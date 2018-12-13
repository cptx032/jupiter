# coding: utf-8

"""Jupiter audio sequencer."""

import os
import Tkinter as tk
import tkFileDialog
import uuid
import time
import threading

import numpy
import pyglet
from boring import draw
from boring.window import SubWindow, Window
from boring.widgets import Label, ExtendedCanvas as Canvas, Button, Entry
from boring.dialog import DefaultDialog


def lerp(a, b, x):
    u"""Linear Interpolation."""
    return a + ((b - a) * x)


SELECT_COLOR = u'#1e90ff'
SELECT_MARK_PADDING_PX = 15
SELECT_LINE_WIDTH = 3

TRACK_LABEL_FONT = ('TkDefaultFont', 8)

# fixme > read pallete from configuration file
COLORS = [
    '#00aacc', '#CD1B00', '#00CD74', '#CD8900', '#CD0066'
]


class DefaultDialogButton(Button):
    def __init__(self, *args, **kwargs):
        Button.__init__(self, *args, **kwargs)
        self.configure(
            relief='flat',
            bg=self.master['bg'],
            highlightthickness=1,
            highlightbackground='#00aacc',
            fg='#999'
        )


class RenameSoundFragmentDialog(DefaultDialog):
    def __init__(self, *args, **kwargs):
        self.track_label = kwargs.pop('track_label', '')
        kwargs.update(button_class=DefaultDialogButton)
        DefaultDialog.__init__(self, *args, **kwargs)

    def body(self, parent):
        self._entry = Entry(
            parent,
            fg='#333',
            text='Rename',
            relief='flat',
            bd=10,
            insertwidth=1
        )
        self._entry.grid(pady=5, padx=5)

        # for some reason that I can't understand
        # even creating a new instance of Entry it will
        # 'insert' a new text to entry, so, every time you
        # rename, the entry will appending old track labels
        # the solution that I found was remove the content
        # before fill the text
        self._entry.delete(0, 'end')
        self._entry.insert('0', self.track_label)
        return self._entry

    def apply(self):
        self.result = self._entry.get()


class JupiterAboutWindow(SubWindow):
    def __init__(self, *args, **kwargs):
        SubWindow.__init__(self, *args, **kwargs)
        self.jupiter_image = tk.PhotoImage(file='jupiter.gif')
        self.enable_escape()
        self.configure(bg=self.master['bg'])
        self.resizable(0, 0)
        Label(
            self, image=self.jupiter_image, bd=0,
            highlightthickness=0
        ).grid(row=0)
        Label(
            self, text=u'Author: @cptx032\nVersion: 0.0.1',
            font=('TkDefaultFont', 10),
            fg='#999', bg=self['bg']
        ).grid(row=1, padx=55, pady=55)
        self.center()


class CanvasButton(draw.RectangleDraw):
    def __init__(self, *args, **kwargs):
        _text = kwargs.pop('text', u'')
        _font = kwargs.pop('font', None)
        draw.RectangleDraw.__init__(self, *args, **kwargs)
        self.text = draw.TextDraw(
            self.canvas, self.x + (self.width / 2),
            self.y + (self.height / 2),
            fill='#000', text=_text,
            font=_font
        )

    def update(self):
        draw.RectangleDraw.update(self)
        self.text.x = self.x + (self.width / 2)
        self.text.y = self.y + (self.height / 2)


class ToggleCanvasButton(CanvasButton):
    def __init__(self, *args, **kwargs):
        self.selected = False
        super(ToggleCanvasButton, self).__init__(*args, **kwargs)

        self.bind(u'<1>', self.click_handler, '+')
        self.text.bind(u'<1>', self.click_handler, '+')
        self.__original_fill = self.fill
        self.update_colors()

    @property
    def original_fill(self):
        return self.__original_fill

    @original_fill.setter
    def original_fill(self, value):
        self.__original_fill = value
        self.update_colors()

    def update_colors(self):
        self.fill = self.original_fill if self.selected else '#000'
        self.outline = self.original_fill
        self.text.fill = '#000' if self.selected else self.original_fill

    def click_handler(self, event=None):
        self.selected = not self.selected
        self.update_colors()


class HorizontalGrid(object):
    def __init__(self, canvas, x, y, width, height, **kwargs):
        self.fill = kwargs.pop('fill', '#444')
        self.track_spacing = kwargs.pop('track_spacing', 40)
        self.tag = uuid.uuid4().hex
        self.canvas = canvas
        self.x = x
        self.y = y
        self.width = width
        self.height = height

        self.draw()

    def draw(self):
        self.canvas.delete(self.tag)
        for y in range(0, self.canvas.winfo_height(), self.track_spacing):
            self.canvas.create_line(
                0, y,
                self.canvas.winfo_width(), y,
                tags=self.tag,
                fill=self.fill,
                dash=(5,)
            )
        for x in range(0, self.canvas.winfo_width(), self.track_spacing):
            self.canvas.create_line(
                x, 0, x, self.canvas.winfo_height(),
                fill=self.fill,
                tags=self.tag,
                dash=(5,)
            )


class JupiterSound(object):
    CHUNK_SIZE = 255

    def __init__(self, path):
        self.path = path
        self.media = pyglet.media.load(self.path)
        self.data = self.get_data()
        self.player = pyglet.media.Player()
        self.player.queue(self.media)
        self.duration = self.media.duration
        self.length = len(self.data)

    def get_data(self):
        """Return raw audio data."""
        raw_data = self.media.get_audio_data(JupiterSound.CHUNK_SIZE).data
        last_data = raw_data
        while last_data:
            last_data = self.media.get_audio_data(JupiterSound.CHUNK_SIZE)
            if last_data:
                raw_data += last_data.data
        return numpy.fromstring(raw_data, 'Int16')

    def play(self):
        if not self.player.playing:
            self.player.seek(0)
            self.player.play()

    def stop(self):
        self.player.seek(0)
        self.player.pause()

    def __del__(self):
        self.stop()


class SoundFragment(draw.RectangleDraw):
    MAX_Y_VALUE = 32767.0

    def __init__(self, main_window, jupiter_sound, start, y, **kwargs):
        # the moment when the sound starts
        self.start = start

        self.main_window = main_window
        _fill = kwargs.pop('fill', COLORS[0])
        self.sound = jupiter_sound
        self.__volume = kwargs.pop('volume', 1.0)

        self.mute = kwargs.pop('mute', False)
        self.solo = kwargs.pop('solo', False)
        self.button_width = kwargs.pop('button_width', 25)
        self.button_height = kwargs.pop('button_height', 25)
        self.__selected = False

        draw.RectangleDraw.__init__(
            self, main_window.main_canvas, self.get_x(), y,
            self.get_width(),
            kwargs.pop('height', 25),
            fill=_fill,
            outline=_fill
        )

        self.bind('<1>', self.mark_as_selected, '+')

        self.mute_btn = ToggleCanvasButton(
            self.canvas,
            self.x,
            self.y - self.button_height,
            self.button_width,
            self.button_height,
            text=u'M',
            fill=self.fill
        )
        self.solo_btn = ToggleCanvasButton(
            self.canvas,
            self.x + self.button_width,
            self.y - self.button_height,
            self.button_width,
            self.button_height,
            text=u'S',
            fill=self.fill
        )
        self.fill_btn = draw.RectangleDraw(
            self.canvas,
            self.x + (self.button_width * 2),
            self.y - self.button_height,
            self.button_width,
            self.button_height,
            fill=self.fill,
            outline=self.fill
        ).bind('<1>', self.rotate_color, '+')
        self.volume_btn = CanvasButton(
            self.canvas,
            self.x + (self.button_width * 3),
            self.y - self.button_height,
            self.button_width,
            self.button_height,
            fill=self.fill,
            outline=self.fill,
            text=str(self.volume),
            font=('TkDefaultFont', 6)
        )
        self.track_label = draw.TextDraw(
            self.canvas,
            self.x + (self.button_width * 4) + 5,
            self.y - (self.button_height / 2),
            anchor='w',
            text=kwargs.pop('track_label', u'TRACK LABEL'),
            fill='#aaa',
            font=TRACK_LABEL_FONT
        ).bind('<1>', self.mark_as_selected, '+')
        self.calculates_sound_lines()
        self.sound_line = draw.LineDraw(
            self.canvas,
            self.get_sound_line_points(),
            fill='#000',
            width=3
        ).bind('<1>', self.mark_as_selected, '+')

        self.selected_mark = draw.RectangleDraw(
            self.canvas,
            0, 0, 0, 0,
            fill='',
            outline=SELECT_COLOR,
            width=SELECT_LINE_WIDTH,
            dash=(5, )
        )

        self.update_component()
        self.enable_drag()

    @property
    def selected(self):
        return self.__selected

    @selected.setter
    def selected(self, value):
        self.__selected = value
        self.update_component()

    def mark_as_selected(self, event=None):
        if not self.main_window.kmap.get('Control_L', False):
            self.main_window.desselect_sound_fragments()
        self.selected = True

    def get_x(self):
        pad_left = self.start * self.main_window.sec_px
        return self.main_window.start_line_left_padding + pad_left

    def get_width(self):
        return int(self.sound.duration * self.main_window.sec_px)

    @property
    def volume(self):
        return self.__volume

    @volume.setter
    def volume(self, value):
        self.__volume = value

    def rotate_color(self, event=None):
        index = COLORS.index(self.fill)
        index += 1
        if index >= len(COLORS):
            index = 0
        self.fill = COLORS[index]
        self.update_component()

    def update_component(self, dx=None, dy=None):
        self.fill_btn.configure(fill=self.fill, outline=self.fill)
        self.configure(outline=self.fill, stipple='gray12')
        self.width = self.get_width()

        # recalculating position
        self.x = self.get_x()

        self.mute_btn.original_fill = self.fill
        self.solo_btn.original_fill = self.fill
        self.volume_btn.configure(fill=self.fill, outline=self.fill)

        if self.selected:
            self.selected_mark.configure(width=SELECT_LINE_WIDTH)
            self.selected_mark.xy = self.x - SELECT_MARK_PADDING_PX, self.y - self.button_height - SELECT_MARK_PADDING_PX
            self.selected_mark.width = self.width + (SELECT_MARK_PADDING_PX * 2)
            self.selected_mark.height = self.height + (SELECT_MARK_PADDING_PX * 2) + self.button_height
        else:
            self.selected_mark.configure(width=0)
            self.selected_mark.xy = 0, 0
            self.selected_mark.size = 0, 0

        self.track_label.x = self.x + (self.button_width * 4) + 5
        self.track_label.y = self.y - (self.button_height / 2)

        self.mute_btn.xy = self.x, self.y - self.button_height
        self.solo_btn.xy = (
            self.x + self.button_width, self.y - self.button_height
        )
        self.fill_btn.xy = (
            self.x + (self.button_width * 2), self.y - self.button_height
        )
        self.volume_btn.xy = (
            self.x + (self.button_width * 3), self.y - self.button_height
        )
        self.sound_line.coords = self.get_sound_line_points()
        self.canvas.update_idletasks()

    def get_sound_line_points(self):
        points = []
        for i in range(0, len(self.sound_line_points), 2):
            points.extend([
                self.sound_line_points[i] + self.x,
                self.sound_line_points[i + 1] + self.y
            ])
        return points

    def calculates_sound_lines(self):
        u"""Cache the points of sound line."""
        width = int(self.sound.duration * self.main_window.sec_px)
        points = []
        samples = 400
        y_offset = self.height / 2.0
        for s in range(samples):
            lerp_x = s / float(samples)
            x = lerp(0, width, lerp_x)
            sample_index = int(lerp(0, len(self.sound.data), lerp_x))
            y = ((self.sound.data[sample_index] * self.height) / SoundFragment.MAX_Y_VALUE) + y_offset
            points.extend([x, y])
        self.sound_line_points = points

    def drag_handler(self, event):
        draw.RectangleDraw.drag_handler(self, event)
        dx = self._drag_initial_distance[0] - event.x
        dy = self._drag_initial_distance[1] - event.y
        distance = self.x - self.main_window.start_line_left_padding
        self.start = distance / self.main_window.sec_px
        self.update_component(dx, dy)

    def play(self):
        self.sound.play()

    def stop(self):
        self.sound.stop()


class MainJupiterWindow(Window):
    def __init__(self):
        Window.__init__(self)

        self.__sec_px = 10
        self.config(bg='#333')
        self.enable_escape()
        self.enable_kmap()
        self.caption = 'Jupiter'
        self.maximize()
        self.update_idletasks()

        self.main_canvas = Canvas(
            self, bd=0, highlightthickness=0,
            bg=self['bg'])
        self.main_canvas.pack(expand='yes', fill='both')
        self.main_canvas.update_idletasks()
        self.horizontal_grid = HorizontalGrid(
            self.main_canvas, 300, 0, self.winfo_width() - 300,
            self.winfo_height())
        self.bind('<o>', self.open_file, '+')
        self.bind('<Button-4>', self.mouse_scroll_up_handler, '+')
        self.bind('<Button-5>', self.mouse_scroll_down_handler, '+')

        self.background = draw.RectangleDraw(
            self.main_canvas, 0, 0,
            self.main_canvas.width, self.main_canvas.height,
            fill='#000',
            stipple='gray12'
        )
        self.background.bind('<1>', self.desselect_sound_fragments, '+')

        self.status_text = draw.TextDraw(
            self.main_canvas,
            20, self.height - 20,
            text=u'', fill='#999',
            anchor='sw'
        )
        self.sec_px_label = draw.TextDraw(
            self.main_canvas,
            self.width - 20,
            self.height - 20,
            text=u'{}px'.format(self.sec_px),
            anchor='se', fill='#999',
            font=('TkDefaultFont', 10, 'bold')
        )

        self.main_canvas.create_text(
            self.width - 20,
            20, text=u'\n\n'.join([
                'o - open wav',
                'b - about',
                'a - select all',
                'r - rename sound'
            ]),
            anchor='ne', fill='#999'
        )

        # how many pixels the start-line is from left side of screen
        self.start_line_left_padding = 200

        # start-line (the vertical line that marks the start of music)
        self.start_line = draw.LineDraw(
            self.main_canvas,
            [
                self.start_line_left_padding, 0, self.start_line_left_padding,
                self.height
            ],
            fill='#674172',
            width=2
        )

        self.play_line = draw.LineDraw(
            self.main_canvas,
            [
                self.start_line_left_padding, 0, self.start_line_left_padding,
                self.height
            ],
            fill='#555',
            width=1
        )
        self.playing = False
        self.start_play = None
        self.bind('<p>', self.toggle_play_pause, '+')

        self.bind('<Up>', self.offset_positive_y_sound_fragments, '+')
        self.bind('<Down>', self.offset_negative_y_sound_fragments, '+')
        self.bind('<a>', self.select_all_sound_fragments, '+')
        self.bind('<r>', self.rename_selected_sound_fragment, '+')
        self.bind('<b>', self.show_about, '+')

        self.sounds = []
        self.main_canvas.focus_force()

    def rename_selected_sound_fragment(self, event=None):
        selected = self.get_selected_sound_fragments()
        if len(selected) > 1:
            return
        s_fragment = selected[0]
        name = RenameSoundFragmentDialog(
            self,
            u'Rename {}'.format(s_fragment.track_label.text),
            track_label=s_fragment.track_label.text
        ).result
        if name:
            s_fragment.track_label.text = name

    def select_all_sound_fragments(self, event=None):
        if len(self.get_selected_sound_fragments()) == len(self.sounds):
            self.desselect_sound_fragments()
        else:
            for sound in self.sounds:
                sound.selected = True

    def offset_positive_y_sound_fragments(self, event=None):
        for sound in self.get_selected_sound_fragments():
            sound.y -= 5
            sound.update_component()

    def offset_negative_y_sound_fragments(self, event=None):
        for sound in self.get_selected_sound_fragments():
            sound.y += 5
            sound.update_component()

    def desselect_sound_fragments(self, event=None):
        for sound in self.sounds:
            sound.selected = False

    def toggle_play_pause(self, event=None):
        if self.playing:
            self.playing = False
            for sound in self.sounds:
                sound.stop()
        else:
            self.playing = True
            self.start_play = time.time()
            self.update_play_line()

    def get_selected_sound_fragments(self):
        return [i for i in self.sounds if i.selected]


    def update_play_line(self):
        duration = time.time() - self.start_play
        x = self.start_line_left_padding
        x += self.sec_px * duration
        self.play_line.coords = [
            x, 0, x, self.height
        ]

        for sound in self.sounds:
            if duration >= sound.start:
                if self.playing:
                    sound.play()
        if self.playing:
            self.after(1, self.update_play_line)

    @property
    def sec_px(self):
        return self.__sec_px

    @sec_px.setter
    def sec_px(self, value):
        self.__sec_px = value
        for sound in self.sounds:
            threading.Timer(0, sound.calculates_sound_lines).start()
            sound.update_component()
        self.sec_px_label.text = u'{}px'.format(self.sec_px)

    def mouse_scroll_up_handler(self, event=None):
        if self.kmap.get(u'Shift_L', False):
            for i in self.sounds:
                i.height += 5
                i.calculates_sound_lines()
                i.update_component()
        else:
            self.sec_px += 1

    def mouse_scroll_down_handler(self, event=None):
        if self.kmap.get(u'Shift_L', False):
            for i in self.sounds:
                i.height -= 5
                if i.height <= 5:
                    i.height = 5
                i.calculates_sound_lines()
                i.update_component()
        else:
            self.sec_px -= 1
            # fixme: put this value in a configuration file?
            if self.sec_px < 5:
                self.sec_px = 5

    def show_about(self, event=None):
        JupiterAboutWindow(self)

    def set_status(self, text):
        self.status_text.xy = 20, self.height - 20
        self.status_text.configure(text=text)
        self.main_canvas.update_idletasks()

    def open_file(self, event=None):
        filenames = tkFileDialog.askopenfilenames(
            filetypes=(
                ('WAV Files', '*.wav'),
            )
        )
        if not filenames:
            return

        for filename in filenames:
            self.set_status(u'Loading {} ...'.format(filename))
            sv = SoundFragment(
                self,
                JupiterSound(filename),
                1.0, 25,
                track_label=os.path.basename(
                    os.path.splitext(filename)[0]).upper()
            )
            self.sounds.append(sv)
        self.set_status('')

if __name__ == '__main__':
    top = MainJupiterWindow()
    top.mainloop()

'''
{
    "sec_px": 10,
    "bpm": 110,
    "sounds": [
        {
            "path": "sounds/base01.wav",
            # color index
            "color": 0,
            "mute": false,
            "solo": false,
            "start": 0.02
        }
    ]
}
# o grid no fundo deve ser o metronomo
# lock fragments
# save
# ctrl+c ctrl+v
# select multiple + move (falta na horizontal)
# editar samples
# gravar samples
# mutar e desmutar por cor
# ao fechar repentinamento o arquivo, estoura um erro
# m -> muta tudo que está selecionado
# undo/redo

# como os sounds estao sendo desenhados em funcao do padding_left
# tlvz nem precise fazer scroll em todo mundo, mas sim só mudar o paddingleft

# possibilidade de adicionar bookmarks em trechos
    # os bookmarks podem ser um ponto no tempo, fixos, ou podem ser relativos
    # aos sound fragments

# bug audacity, apertar seta cima pra ir pra track de cima
# mas se apertar Shift + R ele grava na anterior
# ao solar uma track e apertar shift+r ele toca as que estao mudas
# apertar F2 e alterar o nome da track

# o atalho para desmutar tudo nao funciona (Ctrl + Shift + U)
# psicopato, o pato psicopata
'''