# coding: utf-8

"""Jupiter audio sequencer."""

import os
import uuid
import time
import threading
import audioop
import math
import struct
import wave

import numpy
import pyaudio
from boring import draw
from boring.window import SubWindow, Window, import_tkinter, import_filedialog
from boring.widgets import Label, ExtendedCanvas as Canvas, Button, Entry
from boring.dialog import DefaultDialog


PYAUDIO = pyaudio.PyAudio()
tk = import_tkinter()
filedialog = import_filedialog()


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


class ChangeBPMDialog(DefaultDialog):
    def __init__(self, *args, **kwargs):
        self.bpm = kwargs.pop('bpm', 110)
        kwargs.update(button_class=DefaultDialogButton)
        DefaultDialog.__init__(self, *args, **kwargs)

    def body(self, parent):
        self._entry = Entry(
            parent,
            fg='#333',
            text='BPM',
            relief='flat',
            bd=10,
            insertwidth=1
        )
        self._entry.grid(pady=5, padx=5)
        self._entry.delete(0, 'end')
        self._entry.insert('0', str(self.bpm))
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

    def delete(self):
        draw.RectangleDraw.delete(self)
        self.text.delete()


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


class BPMGrid(object):
    def __init__(self, canvas, sec_px, start_px, bpm, **kwargs):
        self.fill = kwargs.pop('fill', '#444')
        self.tag = uuid.uuid4().hex
        self.canvas = canvas
        self.visible = kwargs.pop('visible', True)

        self.start_px = start_px
        self.__sec_px = sec_px
        self.__bpm = bpm
        self.px_distance = int(self.sec_px / (self.bpm / 60.0))
        self.label = draw.TextDraw(
            self.canvas,
            20, self.canvas.winfo_height() - 60,
            font=('TkDefaultFont', 10, 'bold'),
            anchor='sw', text=u'{} bpms'.format(self.bpm),
            fill='#999',
        )

        self.draw()

    def update_px_distance(self):
        self.px_distance = int(self.sec_px / (self.bpm / 60.0))

    @property
    def bpm(self):
        return self.__bpm

    @bpm.setter
    def bpm(self, value):
        self.__bpm = value
        self.label.text = u'{} bpms'.format(self.bpm)
        self.update_px_distance()
        self.draw()

    @property
    def sec_px(self):
        return self.__sec_px


    @sec_px.setter
    def sec_px(self, value):
        self.__sec_px = value
        self.update_px_distance()
        self.draw()

    def draw(self):
        self.canvas.delete(self.tag)
        if not self.visible:
            return

        for x in xrange(
                self.start_px, self.canvas.winfo_width(), self.px_distance):
            if x < 0:
                continue
            self.canvas.create_line(
                x, 0, x, self.canvas.winfo_height(),
                fill=self.fill,
                tags=self.tag,
                dash=(15,),
            )


class JupiterSound(object):
    CHUNK_SIZE = 255

    def __init__(self, path):
        self.path = path
        self.media = wave.open(self.path, u'rb')
        self.data = self.get_data()
        self.duration = self.media.getnframes() / float(
            self.media.getframerate())
        self.playing = False
        self.volume = 1.0
        self.decibel = 0

    def get_data(self):
        data = self.media.readframes(JupiterSound.CHUNK_SIZE)
        _d = data
        while _d:
            _d = self.media.readframes(JupiterSound.CHUNK_SIZE)
            data += _d
        return numpy.fromstring(data, 'Int16')

    def play(self, seek=0.0):
        if self.playing:
            return


        self.media.rewind()
        self.playing = True

        stream = PYAUDIO.open(
            format=PYAUDIO.get_format_from_width(self.media.getsampwidth()),
            channels=self.media.getnchannels(),
            rate=self.media.getframerate(),
            output=True
        )

        def callback():
            # reading some first bytes to conform 'seek'
            self.media.readframes(int(self.media.getframerate() * seek))

            data = self.media.readframes(JupiterSound.CHUNK_SIZE)
            while self.playing and data:
                data = numpy.fromstring(data, 'Int16') * self.volume
                # python3 error
                data = struct.pack('h' * len(data), *data)

                stream.write(data)
                data = self.media.readframes(JupiterSound.CHUNK_SIZE)
                self.decibel = 20 * math.log10(audioop.rms(data, 2))
            stream.stop_stream()
            stream.close()
            self.playing = False

        threading.Thread(target=callback).start()

    def stop(self):
        self.playing = False

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
            kwargs.pop('height', 50),
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

    def delete(self):
        draw.RectangleDraw.delete(self)
        self.sound_line.delete()
        self.track_label.delete()
        self.selected_mark.delete()
        self.volume_btn.delete()
        self.mute_btn.delete()
        self.fill_btn.delete()
        self.solo_btn.delete()

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

    def play(self, seek=0.0):
        self.sound.play(seek)

    def stop(self):
        self.sound.stop()


class MainJupiterWindow(Window):
    def __init__(self):
        Window.__init__(self)

        self.__sec_px = 20
        self.config(bg='#333')
        self.enable_escape()
        self.enable_kmap()
        self.caption = 'Jupiter'
        self.maximize()
        # self.geometry(u'800x600')
        self.update_idletasks()

        self.main_canvas = Canvas(
            self, bd=0, highlightthickness=0,
            bg=self['bg'])
        self.main_canvas.pack(expand='yes', fill='both')
        self.main_canvas.update_idletasks()
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
        self.background.bind('<1>', self.set_cursor_position, '+')

        self.status_text = draw.TextDraw(
            self.main_canvas,
            20, self.height - 20,
            text=u'', fill='#999',
            anchor='sw'
        )
        self.sec_px_label = draw.TextDraw(
            self.main_canvas,
            20,
            self.height - 40,
            text=u'{}px/sec'.format(self.sec_px),
            anchor='sw', fill='#999',
            font=('TkDefaultFont', 10, 'bold')
        )
        self.play_position_label = draw.TextDraw(
            self.main_canvas,
            20,
            self.height - 20,
            text=u'0min 0sec',
            anchor='sw', fill='#999',
            font=('TkDefaultFont', 10, 'bold')
        )

        self.main_canvas.create_text(
            self.width - 20,
            20, text=u'\n\n'.join([
                'o - open wav',
                'b - change bpm',
                't - about',
                'a - select all',
                'f2 - rename sound',
                'space - play/stop',
                'home - set cursor to start position',
                'end - set cursor to end position'
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
            [0, 0, 0, 0],
            fill='#2ecc71',
            width=5
        )
        self.cursor_line = draw.LineDraw(
            self.main_canvas,
            [
                self.start_line_left_padding, 0, self.start_line_left_padding,
                self.height
            ],
            fill='#3498db',
            width=2
        )

        self.playing = False
        # the point in time that start to play (time of computer)
        self.start_play = None
        # the point in timeline that start to play (time of music)
        self.start_seek = None

        self.bind('<space>', self.toggle_play_pause, '+')
        self.bind('<Delete>', self.delete_fragments, '+')

        self.bind('<Up>', self.offset_positive_y_sound_fragments, '+')
        self.bind('<Down>', self.offset_negative_y_sound_fragments, '+')
        self.bind('<a>', self.select_all_sound_fragments, '+')
        self.bind('<F2>', self.rename_selected_sound_fragment, '+')
        self.bind('<b>', self.change_bpm, '+')
        self.bind('<t>', self.show_about, '+')
        self.bind('<Home>', self.set_cursor_to_start_position, '+')
        self.bind('<End>', self.set_cursor_to_end_position, '+')

        self.sounds = []
        self.main_canvas.focus_force()

        self.__bpm = 110
        self.bpm_grid = BPMGrid(
            self.main_canvas,
            self.sec_px, self.start_line_left_padding,
            self.bpm
        )

    @property
    def bpm(self):
        return self.__bpm

    @bpm.setter
    def bpm(self, value):
        self.__bpm = value
        self.bpm_grid.bpm = self.bpm

    def set_cursor_to_start_position(self, event=None):
        self.cursor_line.coords = [
            self.start_line_left_padding, 0,
            self.start_line_left_padding, self.height
        ]

    def set_cursor_to_end_position(self, event=None):
        if len(self.sounds) == 0:
            return
        seek = self.sounds[0].start + self.sounds[0].sound.duration
        for sound in self.sounds[1:]:
            sound_seek = sound.start + sound.sound.duration
            if sound_seek > seek:
                seek = sound_seek
        x = self.start_line_left_padding + (self.sec_px * seek)
        if x > self.width:
            # the cursor will be in the end of canvas/window
            # just padded some pixels
            pad = 20
            px = seek * self.sec_px
            self.set_start_label_to(self.width - pad - px)
            x = self.start_line_left_padding + (self.sec_px * seek)
        self.cursor_line.coords = [
            x, 0,
            x, self.height
        ]

    def set_start_label_to(self, px):
        cursor = self.cursor_line.coords[0] - self.start_line_left_padding
        self.start_line_left_padding = int(px)

        self.start_line.coords = [
            self.start_line_left_padding, 0,
            self.start_line_left_padding, self.height
        ]
        self.cursor_line.coords = [
            px + cursor, 0,
            px + cursor, self.height
        ]
        for i in self.sounds:
            i.update_component()
        self.bpm_grid.start_px = self.start_line_left_padding
        self.bpm_grid.draw()

    def set_cursor_position(self, event):
        x = event.x
        if x < self.start_line_left_padding:
            x = self.start_line_left_padding
        self.cursor_line.coords = [
            x, 0, x,
            self.height
        ]

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

    def change_bpm(self, event=None):
        bpm = ChangeBPMDialog(
            self,
            u'Change BPM',
            bpm=self.bpm
        ).result
        if bpm:
            self.bpm = int(bpm)

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

    def delete_fragments(self, event=None):
        for sound in self.get_selected_sound_fragments():
            self.sounds.remove(sound)
            sound.delete()

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
            dx = self.cursor_line.coords[0] - self.start_line_left_padding
            self.start_seek = dx / float(self.sec_px)
            self.start_play = time.time()
            self.update_play_line()

    def get_selected_sound_fragments(self):
        return [i for i in self.sounds if i.selected]


    def update_play_line(self):
        duration = time.time() - self.start_play

        x = self.start_line_left_padding + (self.start_seek * self.sec_px)
        x += self.sec_px * duration
        self.play_line.coords = [
            x, 0, x, self.height
        ]

        secs_playing = self.start_seek + duration
        minutes_playing = int(secs_playing / 60.0)
        secs_playing = secs_playing % 60.0
        self.play_position_label.text = u'{}min {:.2f}secs'.format(
            minutes_playing, secs_playing
        )

        actual_seek = self.start_seek + duration
        # there is a better way to avoid loop all fragments?
        for sound in self.sounds:
            interval = [
                sound.start,
                sound.start + sound.sound.duration
            ]
            if actual_seek >= interval[0] and actual_seek <= interval[1]:
                seek_to_play = actual_seek - sound.start
                if self.playing:
                    sound.play(seek_to_play)
        if self.playing:
            self.after(1, self.update_play_line)
        else:
            self.play_line.coords = [0, 0, 0, 0]
            self.play_position_label.text = '0min 0sec'

    @property
    def sec_px(self):
        return self.__sec_px

    @sec_px.setter
    def sec_px(self, value):
        self.__sec_px = value
        for sound in self.sounds:
            threading.Timer(0, sound.calculates_sound_lines).start()
            sound.update_component()
        self.sec_px_label.text = u'{}px/sec'.format(self.sec_px)

    def mouse_scroll_up_handler(self, event=None):
        if self.kmap.get(u'Shift_L', False):
            self.set_start_label_to(self.start_line_left_padding + 15)
        elif self.kmap.get('Control_L'):
            self.sec_px += 1
            self.bpm_grid.sec_px = self.sec_px
            self.bpm_grid.draw()

    def mouse_scroll_down_handler(self, event=None):
        if self.kmap.get(u'Shift_L', False):
            self.set_start_label_to(self.start_line_left_padding - 15)
        elif self.kmap.get('Control_L'):
            self.sec_px -= 1
            # fixme: put this value in a configuration file?
            if self.sec_px < 5:
                self.sec_px = 5

            self.bpm_grid.sec_px = self.sec_px
            self.bpm_grid.draw()

    def show_about(self, event=None):
        JupiterAboutWindow(self)

    def set_status(self, text):
        self.status_text.xy = self.width / 2, self.height - 20
        self.status_text.configure(text=text)
        self.main_canvas.update_idletasks()

    def open_file(self, event=None):
        filenames = filedialog.askopenfilenames(
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
                1.0, 100,
                track_label=os.path.basename(
                    os.path.splitext(filename)[0]).upper()
            )
            self.sounds.append(sv)
        self.set_status('')

if __name__ == '__main__':
    top = MainJupiterWindow()
    top.mainloop()
    PYAUDIO.terminate()

'''
# save
# ctrl+c ctrl+v
# select multiple + move (falta na horizontal)
# editar samples
# gravar samples
# mutar e desmutar por cor
# m -> muta tudo que está selecionado
# ao fechar tela dar um stop em todos os fragments
# undo/redo

# a leitura não ser mais do .media, assim o stream precisa ser direto de um
# stringio pra poder fazer edição dos samples sem salvar os arquivos em outros
# waves

# possibilidade de adicionar bookmarks em trechos
    # os bookmarks podem ser um ponto no tempo, fixos, ou podem ser relativos
    # aos sound fragments
# o play-line só aparece quando houver som tocando

# bug audacity, apertar seta cima pra ir pra track de cima
# mas se apertar Shift + R ele grava na anterior
# ao solar uma track e apertar shift+r ele toca as que estao mudas
# apertar Tab para alternar de uma base para outra
# permitir alterar o volume de uma parte especifica

# permitir copiar um fragment e as alterações de volume que
# se fizerem se repete a nao ser que se queira "desconectar"
# psicopato, o pato psicopata
'''
