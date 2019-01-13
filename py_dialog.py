#!/usr/bin/env python
# coding: utf-8
"""PyDialog is a tool to create dialogs."""

import sys

VERSION = '0.0.1'

HELP_TEXT = u'''Py Dialog v{}

Tool for dialogs creation

Usage:
  py_dialog [-opt] | [--opt value]
  where opt is the option list below

File Dialog Options
  -fd, -file_dialog <title>
      Opens a file chooser dialog

Text Dialog Options
  -td, -text_dialog
      Opens a text dialog
  --tdd, --text_dialog_default
      Sets the default text showed in entry field
  --tdl, --text_dialog_label
      Sets the label to use in input

Color Dialog Options
  -cd, -color_dialog
      Opens a color chooser
  --cdd, --color_dialog_default
      Sets the default color in #RRGGBB format.
      If empty the color will be black.
      Enclosure the color with  double quotes to avoid bash commentaries
  --cdof, --color_dialog_output_format
      Sets the format of output. Valid values are:
      - rgb (outputs a string in #RRGGBB format)
      - integer (outputs a decimal integer representing the color)
        the integer outputed is the value of 0xRRGGBB
      The default format of output is integer

General Options
  --dt, --dialog_title <title>
      Sets the window title of file dialog
  -nl, -new_line                       Puts a new line character at the end
  -h, --help                           Show this help
  -v, --version                        Show version
'''.format(VERSION)


def get_tk_module():
    """Return tkinter module. Py2/3 compatible."""
    try:
        import Tkinter as tk
        return tk
    except ImportError:
        pass

    import tkinter as tk
    return tk


def get_tk_file_dialog_module():
    """Return file dialog module. Py2/3 compatible."""
    try:
        import tkFileDialog as tfd
        return tfd
    except ImportError:
        pass

    from tkinter import filedialog as tfd
    return tfd


def get_tk_color_chooser_module():
    """Return the color chooser module. Py2/3 compatible."""
    try:
        import tkColorChooser as tcc
        return tcc
    except ImportError:
        from tkinter import colorchooser as tcc
        return tcc


tk = get_tk_module()
tfd = get_tk_file_dialog_module()
tcc = get_tk_color_chooser_module()


class DefaultDialog(tk.Toplevel):
    """
    Class to open dialogs.
    This class is intended as a base class for custom dialogs
    """
    def __init__(self, parent, title=None, show_in_start=True):
        """
        Initialize a dialog.
        Arguments:
            parent -- a parent window (the application window)
            title -- the dialog title
            button_class -- the class used to render default buttons
        """
        tk.Toplevel.__init__(self, parent)
        self['bg'] = parent['bg']

        self.withdraw()
        # remain invisible for now
        # If the master is not viewable, don't
        # make the child transient, or else it
        # would be opened withdrawn
        if parent.winfo_viewable():
            self.transient(parent)

        if title:
            self.title(title)

        self.parent = parent
        self.resizable(0, 0)

        self.result = None

        body = tk.Frame(self)
        self.initial_focus = self.body(body)
        body.pack(padx=5, pady=5, expand='yes', fill='both')

        self.buttonbox()

        if not self.initial_focus:
            self.initial_focus = self

        self.protocol('WM_DELETE_WINDOW', self.cancel)

        self.center()
        self.deiconify()

        self.initial_focus.focus_set()

        if show_in_start:
            self.show()
        else:
            self.withdraw()

    def destroy(self):
        self.initial_focus = None
        tk.Toplevel.destroy(self)

    def center(self):
        """Centralize the window in the screen."""
        self.update_idletasks()
        sw = int(self.winfo_screenwidth())
        sh = int(self.winfo_screenheight())
        ww = int(self.winfo_width())
        wh = int(self.winfo_height())
        xpos = (sw / 2) - (ww / 2)
        ypos = (sh / 2) - (wh / 2)
        self.geometry('+%d+%d' % (xpos, ypos))

    def body(self, master):
        """Create dialog body.

        return widget that should have initial focus.
        This method should be overridden, and is called
        by the __init__ method.
        """
        pass

    def show(self):
        # wait for window to appear on screen before calling grab_set
        self.attributes('-top', 1)
        self.wait_visibility()
        self.grab_set()
        self.wait_window(self)

    def buttonbox(self):
        """Add standard button box.

        override if you do not want the standard buttons
        """
        box = tk.Frame(self)

        tk.Button(box, text='OK', command=self.ok).pack(
            side='left', padx=5, pady=5
        )
        tk.Button(box, text='Cancel', command=self.cancel).pack(
            side='left', padx=5, pady=5
        )

        self.bind('<Return>', self.ok)
        self.bind('<Escape>', self.cancel)

        box.pack(side='right')

    def ok(self, event=None):
        if not self.validate():
            self.initial_focus.focus_set()
            return

        self.withdraw()
        self.update_idletasks()

        try:
            self.apply()
        finally:
            self.cancel()

    def cancel(self, event=None):
        # put focus back to the parent window
        if self.parent is not None:
            self.parent.focus_set()
        self.destroy()

    def validate(self):
        """Calidate the data.

        This method is called automatically to validate the data before the
        dialog is destroyed. By default, it always validates OK.
        """
        return 1  # override

    def apply(self):
        """Process the data.

        This method is called automatically to process the data, *after*
        the dialog is destroyed. By default, it does nothing.
        """
        pass  # override


class TextDialog(DefaultDialog):
    def __init__(self, *args, **kwargs):
        self.default_value = kwargs.pop('default_value', '')
        self._label = kwargs.pop('label', '')
        DefaultDialog.__init__(self, *args, **kwargs)

    def body(self, parent):
        if self._label:
            tk.Label(parent, text=self._label).grid(
                pady=5, padx=5, sticky='nw'
            )
        self._entry = tk.Entry(
            parent,
            fg='#333',
            relief='flat',
            bd=10,
            insertwidth=1
        )
        self._entry.grid(pady=5, padx=5)
        self._entry.insert(0, self.default_value)
        return self._entry

    def apply(self):
        self.result = self._entry.get()


def has_arguments(*arguments):
    """Return True if argument in in command line arguments."""
    return any([arg in sys.argv for arg in arguments])


def get_argument_value(argument):
    """Return the value of argument.

    Doesn't treat ValueError when argument is not passed, so
    use only before use 'has_argument' function.
    If none value is passed to argument 'None' is returned.
    """
    try:
        return sys.argv[sys.argv.index(argument) + 1]
    except IndexError:
        return None


def get_arg(args, default=None):
    """Return the value gived for a argument."""
    for arg_name in args:
        if has_arguments(arg_name):
            value = get_argument_value(arg_name)
            if value is None:
                return default
            return value
    return default


top = tk.Tk()
top.title('py_dialog')
top.withdraw()

if has_arguments('-h', '--help'):
    sys.stdout.write(HELP_TEXT)

elif has_arguments('-v', '--version'):
    sys.stdout.write(VERSION)

elif has_arguments('-fd', '-file_dialog'):
    fd_kwargs = {
        'title': get_arg(['--dt', '--dialog_title'], default='Open File')
    }
    # fixme > include other file open dialog options
    filename = tfd.askopenfilename(**fd_kwargs)
    if filename:
        sys.stdout.write(filename)

elif has_arguments('-td', '-text_dialog'):
    kwargs = {
        'title': get_arg(['--dt', '--dialog_title'], default='Input'),
        'default_value': get_arg(
            ['--text_dialog_default', '--tdd'], default=''
        ),
        'label': get_arg(['--tdl', '--text_dialog_label'], default=''),
    }
    result = TextDialog(
        top,
        **kwargs
    ).result
    sys.stdout.write(result or '')

elif has_arguments('-cd', '-color_dialog'):
    kwargs = {
        'title': get_arg(['--dt', '--dialog_title'], default='Input'),
        'parent': top,
        'initialcolor': get_arg(
            ['--cdd', '--color_dialog_default'], default='#000000'
        )
    }
    rgbtuple, hexcode = tcc.askcolor(**kwargs)
    if hexcode is not None:
        output_format = get_arg(
            ['--cdof', '--color_dialog_output_format'], default='integer'
        )
        if output_format == 'integer':
            r, g, b = rgbtuple
            sys.stdout.write(str((r << 16) + (g << 8) + b))
        elif output_format == 'rgb':
            sys.stdout.write(hexcode)


if has_arguments('-nl', '-new_line'):
    sys.stdout.write('\n')
