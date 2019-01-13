#include <math.h>
#include <string>
#include <iostream>
#include <thread>
#include <chrono>
#include <unordered_map>
#include <SDL2/SDL.h>
#include <SDL2/SDL_ttf.h>
#include <SDL2/SDL_mixer.h>
#include <vector>
#include "RtMidi.h"


std::string get_ouput_exec(std::string command) {
    FILE *file_object = NULL;
    char result_string[1024];
    file_object = popen(command.c_str(), "r");
    if (file_object == NULL) {
        return "";
    }
    if (fgets(result_string, 1024, file_object) != NULL) {
        return result_string;
    }

    // fixme > pclose?
    return "";
}

int get_integer_dialog(std::string label) {
	std::string port = get_ouput_exec("./py_dialog.py -td --tdl " + label);
	return atoi(port.c_str());
}

std::string get_file_name() {
	return get_ouput_exec("./py_dialog.py -fd");
}


class JupiterDraw {
public:
	virtual void draw(SDL_Renderer *renderer) = 0;
	virtual bool is_inside(int x, int y) = 0;
};


class JupiterText : public JupiterDraw {
public:
	std::string text;
	SDL_Color color;
	bool visible;
	TTF_Font* font;
	int x, y;
	SDL_Rect rect;
	SDL_Texture* texture;

	JupiterText(int x, int y, int font_size = 12): x(x), y(y){
		this->visible = true;
		this->font = TTF_OpenFont("OpenSans-Regular.ttf", font_size);
		this->set_color(0xAAAAAA);
		this->texture = NULL;
	}

	void set_color(int color) {
		this->color = {
			(Uint8)(color >> 16),
			(Uint8)((color & 0x00ff00) >> 8),
			(Uint8)(color & 0x0000ff)
		};
	}

	JupiterText* set_text(std::string text, SDL_Renderer *renderer) {
		this->text = text;
		SDL_Surface* surface = TTF_RenderText_Solid(
			this->font, this->text.c_str(), this->color
		);

		if (this->texture != NULL) {
			SDL_DestroyTexture(this->texture);
		}
		this->texture = SDL_CreateTextureFromSurface(
			renderer, surface
		);

		TTF_SizeText(
			this->font, this->text.c_str(), &this->rect.w, &this->rect.h
		);
		SDL_FreeSurface(surface);

		return this;
	}


	void draw(SDL_Renderer* renderer) {
		if (!this->visible)
			return;

		this->rect.x = this->x;
		this->rect.y = this->y;
		SDL_RenderCopy(renderer, texture, NULL, &this->rect);
	}

	bool is_inside(int x, int y) {
		bool in_x = x >= this->rect.x && x <= (this->rect.x + this->rect.w);
		if (!(x >= this->rect.x && x <= (this->rect.x + this->rect.w))) {
			return false;
		}
		return y >= this->rect.y && y <= (this->rect.y + this->rect.h);
	}
};


class JupiterPolygon : public JupiterDraw {
public:
	int color;
	std::vector<int> coords;
	bool visible;

	int x_offset;
	int y_offset;

	float x_scale;
	float y_scale;

	JupiterPolygon(int color) {
		this->visible = true;
		this->color = color;

		this->x_offset = 0;
		this->y_offset = 0;

		this->x_scale = 1;
		this->y_scale = 1;

		this->coords = {};
	}

	bool is_inside(int x, int y) {
		// no supported for polygons yet
		return false;
	}

	void draw(SDL_Renderer *renderer) override {
		if (!this->visible)
			return;

		if (this->coords.size() < 2)
			return;

		SDL_SetRenderDrawColor(
			renderer,
			this->color >> 16,
			(this->color & 0x00ff00) >> 8,
			this->color & 0x0000ff,
			255
		);

		float x1, y1, x2, y2;

		for (int i=0; i < this->coords.size(); i += 4) {
			x1 = (this->coords[i] * this->x_scale) + this->x_offset;
			y1 = (this->coords[i + 1] * this->y_scale) + this->y_offset;

			x2 = (this->coords[i + 2] * this->x_scale) + this->x_offset;
			y2 = (this->coords[i + 3] * this->x_scale) + this->x_offset;
			SDL_RenderDrawLine(
				renderer, x1, y1,
				x2, y2
			);
		}
	}
};


class JupiterRectangle : public JupiterDraw {
public:
	int color;
	SDL_Rect rect;
	bool visible = true;
	bool filled = false;

	JupiterRectangle() {
		this->rect.x = 0;
		this->rect.y = 0;
		this->rect.w = 0;
		this->rect.h = 0;
		this->color = 0x000000;
	}

	JupiterRectangle(int x, int y, int width, int height, int color) {
		this->rect.x = x;
		this->rect.y = y;
		this->rect.w = width;
		this->rect.h = height;
		this->color = color;
	}

	bool is_inside(int x, int y) {
		bool in_x = x >= this->rect.x && x <= (this->rect.x + this->rect.w);
		if (!(x >= this->rect.x && x <= (this->rect.x + this->rect.w))) {
			return false;
		}
		return y >= this->rect.y && y <= (this->rect.y + this->rect.h);
	}

	void draw(SDL_Renderer *renderer) override {
		if (!this->visible)
			return;

		SDL_SetRenderDrawColor(
			renderer,
			this->color >> 16,
			(this->color & 0x00ff00) >> 8,
			this->color & 0x0000ff,
			255
		);
		if (this->filled)
			SDL_RenderFillRect(renderer, &this->rect);
		else
			SDL_RenderDrawRect(renderer, &this->rect);
	}
};


class JupiterFragmentBase : public JupiterRectangle {
public:
	// the position in music
	float seek;

	// the duration of sound in seconds
	float duration;

	JupiterFragmentBase() {
	}

	void update(int sec_px, int start_line) {
		this->rect.x = (int)(start_line + (this->seek * sec_px));
		this->rect.w = (int)(sec_px * this->duration);
	}
};

class JupiterMIDIFragment : public JupiterFragmentBase {
public:
	bool selected = false;
	int midi_code;
	JupiterRectangle *selection_rect = NULL;
	int selection_pad = 5;
	JupiterMIDIFragment(int code, int y, float seek, float duration, int color) {
		this->rect.y = y;
		this->filled = true;
		this->seek = seek;
		this->duration = duration;
		this->midi_code = code;

		// fixme > create a param for this
		this->rect.h = 10;

		this->color = color;

		this->selection_rect = new JupiterRectangle(
			this->rect.x - this->selection_pad,
			this->rect.y - this->selection_pad,
			this->rect.w + this->selection_pad,
			this->rect.h + this->selection_pad,
			0x00aacc
		);
	}

	void update_selection_rect() {
		this->selection_rect->rect.x = this->rect.x - this->selection_pad;
		this->selection_rect->rect.y = this->rect.y - this->selection_pad;
		this->selection_rect->rect.w = this->rect.w + this->selection_pad * 2;
		this->selection_rect->rect.h = this->rect.h + this->selection_pad * 2;
	}

	void draw(SDL_Renderer *renderer) override {
		if (this->selected && this->visible) {
			this->update_selection_rect();
			this->selection_rect->draw(renderer);
		}
		JupiterFragmentBase::draw(renderer);
	}
};

// fixme > set volume of midi
// fixme > select many midis and align them in vertical
// fixme > select many midis and correct bpms


class JupiterWindow {
public:
	bool kmap[1024];

	SDL_Window* window = NULL;
	SDL_Renderer* renderer = NULL;
	std::vector<JupiterDraw*> draws;
	bool running = true;
	bool playing = false;
	int clear_color;
	JupiterPolygon *start_line = NULL;

	// fixme > change this with a command
	int bpm = 110;
	JupiterText *bpm_label = NULL;
	JupiterPolygon *bpm_lines = NULL;

	int sec_px = 20;
	JupiterText *sec_px_label = NULL;
	int sec_px_increase = 5;
	int min_sec_px = 5;

	JupiterPolygon *cursor_line = NULL;

	JupiterPolygon *play_line = NULL;

	// the point in time that started to play (computer time)
	Uint32 start_play;

	// the point in the timeline that started to play (music seek time)
	float start_seek;

	JupiterText *play_position_label = NULL;

	RtMidiIn *midi_in = NULL;
	std::vector<unsigned char> midi_message;
	float last_midi_seek = 0.f;
	std::vector<JupiterMIDIFragment*> midis;
	std::unordered_map<int, int> midi_colors;
	std::unordered_map<int, Mix_Chunk*> midi_sounds;
	Mix_Chunk *default_midi_sound = NULL;
	int default_midi_color = 0xe74c3c;
	int midi_port = 1;
	// if sound is played when midi is played
	bool play_midi_real_time = true;

	JupiterWindow(const char* title) {
		// initializing kmap
		for (int i=0; i < 1024; i++) {
			this->kmap[i] = false;
		}

		this->clear_color = 0x333333;
		SDL_Init(SDL_INIT_EVERYTHING);
		TTF_Init();
		Mix_OpenAudio(44100, MIX_DEFAULT_FORMAT, 2, 2048);
		this->window = SDL_CreateWindow(
			title, SDL_WINDOWPOS_UNDEFINED,
			SDL_WINDOWPOS_UNDEFINED,
			640,
			480,
			SDL_WINDOW_MAXIMIZED | SDL_WINDOW_RESIZABLE
		);
		this->renderer = SDL_CreateRenderer(
			this->window, -1, SDL_RENDERER_ACCELERATED
		);

		// music start indicator line
		this->start_line = new JupiterPolygon(0x674172);
		this->set_start_line_to(200);
		this->add(this->start_line);

		this->sec_px_label = new JupiterText(20, 0);
		this->update_sec_px_label();
		this->add(this->sec_px_label);

		this->bpm_label = new JupiterText(20, 0);
		this->add(this->bpm_label);
		this->bpm_lines = new JupiterPolygon(0x555555);
		this->add(this->bpm_lines);
		this->update_bpm();

		this->cursor_line = new JupiterPolygon(0x3498db);
		this->set_cursor_position(this->get_start_line_pos());
		this->add(this->cursor_line);

		this->play_line = new JupiterPolygon(0x2ecc71);
		this->play_line->visible = false;
		this->add(this->play_line);

		this->play_position_label = new JupiterText(20, 0);
		this->play_position_label->visible = false;
		this->add(this->play_position_label);

		this->init_midi_colors();
		this->init_midi_sounds();
	}

	void add(JupiterDraw *draw) {
		this->draws.push_back(draw);
	}

	int get_width() {
		int width, height;
		SDL_GetWindowSize(this->window, &width, &height);
		return width;
	}

	int get_height() {
		int width, height;
		SDL_GetWindowSize(this->window, &width, &height);
		return height;
	}

	~JupiterWindow() {
		delete this->midi_in;
		delete this->start_line;
		delete this->default_midi_sound;
		delete this->sec_px_label;
		delete this->bpm_label;
		delete this->bpm_lines;
		delete this->cursor_line;
		delete this->play_line;
		delete this->play_position_label;
		SDL_DestroyRenderer(this->renderer);
		SDL_DestroyWindow(this->window);
		Mix_Quit();
		SDL_Quit();
		// fixme > delete all others
	}

	void init_midi_colors() {
		this->midi_colors[36] = 0xf44336;
		this->midi_colors[38] = 0x9c27b0;
		this->midi_colors[45] = 0x3f51b5;
		this->midi_colors[46] = 0xe91e63;
		this->midi_colors[48] = 0x2196f3;
		this->midi_colors[49] = 0x009688;
		this->midi_colors[51] = 0x673ab7;
		this->midi_colors[57] = 0x8bc34a;
		this->midi_colors[59] = 0xcddc39;
	}

	void init_midi_sounds() {
		this->default_midi_sound = Mix_LoadWAV(
			"./wavdrumkit/click.wav"
		);
		this->midi_sounds[36] = Mix_LoadWAV("wavdrumkit/bumbo.wav");
		this->midi_sounds[46] = Mix_LoadWAV("wavdrumkit/chimbal.wav");
		this->midi_sounds[38] = Mix_LoadWAV("wavdrumkit/caixa.wav");
		this->midi_sounds[51] = Mix_LoadWAV("wavdrumkit/ride-bow.wav");
		this->midi_sounds[59] = Mix_LoadWAV("wavdrumkit/ride-bell.wav");
		this->midi_sounds[49] = Mix_LoadWAV("wavdrumkit/crash.wav");
		this->midi_sounds[57] = Mix_LoadWAV("wavdrumkit/crash01.wav");
		this->midi_sounds[48] = Mix_LoadWAV("wavdrumkit/tom00.wav");
		this->midi_sounds[45] = Mix_LoadWAV("wavdrumkit/tom01.wav");

	}

	void clear() {
		SDL_SetRenderDrawColor(
			this->renderer,
			this->clear_color >> 16,
			(this->clear_color & 0x00ff00) >> 8,
			this->clear_color & 0x0000ff,
			255
		);
		SDL_RenderClear(this->renderer);
	}

	void set_cursor_position(int px) {
		if (px < this->get_start_line_pos()) {
			px = this->get_start_line_pos();
		}
		this->cursor_line->coords = {
			px, 0, px, this->get_height(),
			px - 1, 0, px - 1, this->get_height(),
			px - 2, 0, px - 2, this->get_height(),
		};
	}

	void set_start_line_to(int px) {
		this->start_line->coords = {
			px, 0, px, this->get_height(),
			px - 2, 0, px - 2, this->get_height(),
		};
	}

	int get_start_line_pos() {
		return this->start_line->coords[0];
	}

	void update_start_line_size() {
		int x = this->get_start_line_pos();
		this->start_line->coords = {
			x, 0, x, this->get_height(),
			x - 2, 0, x - 2, this->get_height(),
		};
	}

	void play_midi_sound(int midi_code) {
		if (this->midi_sounds.count(midi_code)) {
			Mix_PlayChannel(-1, this->midi_sounds[midi_code], 0);
		}
		else {
			Mix_PlayChannel(-1, this->default_midi_sound, 0);
		}
	}

	void draw() {
		if (this->playing) {
			float duration = (SDL_GetTicks() - this->start_play) / 1000.f;
			new std::thread(&JupiterWindow::play_midis_at, duration);
			float x = this->get_start_line_pos() + (this->start_seek * this->sec_px);
			x += this->sec_px * duration;

			this->play_line->coords = {
				(int)x, 0, (int)x, this->get_height()
			};

			float secs_playing = this->start_seek + duration;
			int minutes_playing = (int)(secs_playing / 60.f);
			this->play_position_label->set_text(
				std::to_string(minutes_playing) + "min " + std::to_string(fmod(secs_playing, 60.f)) + "sec",
				this->renderer
			);
			this->play_position_label->y = this->get_height() - 20;
			this->play_position_label->x = this->get_width() / 2;

			// fixme > separate this in a diferent thread
			// std::this_thread::sleep_for(std::chrono::milliseconds(x));
			double stamp = this->midi_in->getMessage(&midi_message);
			if (this->midi_message.size() > 0 && (int)this->midi_message[0] == 0x90) {
				std::cout << "midi " << stamp << " " << duration << " " << (int)this->midi_message[0] << " " << 0x80 << std::endl;
				int midi_code = (int)this->midi_message[1];
				JupiterMIDIFragment *rec = new JupiterMIDIFragment(
					// midi code
					midi_code,

					// y coord
					midi_code * 8,

					// seek
					duration,

					// duration
					0.1f,

					// color
					this->midi_colors.count(midi_code) ? this->midi_colors[midi_code] : this->default_midi_color
				);
				rec->update(this->sec_px, this->get_start_line_pos());
				this->midis.push_back(rec);
				this->add(rec);

				if (this->play_midi_real_time) {
					this->play_midi_sound(midi_code);
				}
			}
		}
		this->clear();
		for (int i=0; i < this->draws.size(); i++) {
			this->draws[i]->draw(this->renderer);
		}
		SDL_RenderPresent(this->renderer);
	}

	void play_midis_at(float duration) {
		for (int i=0; i < this->midis.size(); i++) {
			//
		}
	}

	void mainloop() {
		SDL_Event event;
		while(this->running) {
			while(SDL_PollEvent(&event)) {
				if((SDL_QUIT == event.type) ||
					( SDL_KEYDOWN == event.type && SDL_SCANCODE_ESCAPE == event.key.keysym.scancode ) ) {
					this->running = false;
					break;
				}
				else if (SDL_MOUSEWHEEL == event.type) {
					this->treat_mouse_wheel(event.wheel.y);
				}
				else if (SDL_KEYDOWN == event.type) {
					this->kmap[event.key.keysym.scancode] = true;

					if (event.key.keysym.scancode == SDL_SCANCODE_SPACE) {
						if (this->playing) {
							this->play_line->visible = false;
							this->play_position_label->visible = false;
							if (this->midi_in != NULL) {
								delete this->midi_in;
								this->midi_in = NULL;
							}
						}
						else {
							// recreating every play to clear the time stamp
							// between
							this->midi_in = new RtMidiIn(
								RtMidi::Api::LINUX_ALSA,
								"Jupiter"
							);
							this->midi_in->ignoreTypes(false, false, false);
							this->midi_in->openPort(this->midi_port);

							this->play_line->visible = true;
							this->play_position_label->visible = true;
							this->start_play = SDL_GetTicks();
							this->start_seek = (this->cursor_line->coords[0] - this->get_start_line_pos()) / (float)this->sec_px;
						}
						this->playing = !this->playing;
					}
					else if (event.key.keysym.scancode == SDL_SCANCODE_P) {
						this->choose_midi_port();
					}
					else if (event.key.keysym.scancode == SDL_SCANCODE_S) {
						new std::thread(&JupiterWindow::select_similar_midi, this);
					}
					else if (event.key.keysym.scancode == SDL_SCANCODE_UP) {
						new std::thread(&JupiterWindow::up_key_handler, this);
					}
					else if (event.key.keysym.scancode == SDL_SCANCODE_DOWN) {
						new std::thread(&JupiterWindow::down_key_handler, this);
					}
					else if (event.key.keysym.scancode == SDL_SCANCODE_C) {
						new std::thread(&JupiterWindow::change_midi_sound, this);
					}
					else if (event.key.keysym.scancode == SDL_SCANCODE_DELETE) {
						new std::thread(&JupiterWindow::delete_selected, this);
					}
				}
				else if (SDL_KEYUP == event.type) {
					this->kmap[event.key.keysym.scancode] = false;
				}
				else if (SDL_WINDOWEVENT == event.type && event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED) {
					this->update_bpm();
					this->update_sec_px_label();
					this->update_start_line_size();
					this->set_cursor_position(this->cursor_line->coords[0]);
				}
				else if (SDL_MOUSEBUTTONDOWN == event.type) {
					if (SDL_BUTTON_LEFT == event.button.button) {
						std::thread *t = new std::thread(
							&JupiterWindow::select_midi_handler, this,
							event.button.x, event.button.y
						);
					}
				}
			}
			this->draw();
		}
	}

	void delete_selected() {
		std::vector<int> indexes;
		for (int i=0; i < this->midis.size(); i++) {
			if (this->midis[i]->selected) {
				// fixme > the object is still in list
				// the correct is delete it
				this->midis[i]->visible = false;
				indexes.push_back(i);
			}
		}

		int count = 0;

		for (int i=0; i < indexes.size(); i++) {
			this->midis.erase(this->midis.begin() + indexes[i] - count);
			count += 1;
		}
	}

	void change_midi_sound() {
		// fixme > test this
		JupiterMIDIFragment *midi = NULL;
		for (int i=0; i < this->midis.size(); i++) {
			if (this->midis[i]->selected) {
				midi = this->midis[i];
				break;
			}
		}
		if (midi == NULL) {
			return;
		}
		std::string file_name = get_file_name();
		if (file_name.size()) {
			this->midi_sounds[midi->midi_code] = Mix_LoadWAV(file_name.c_str());
		}
	}

	void up_key_handler() {
		for (int i=0; i < this->midis.size(); i++) {
			if (this->kmap[SDL_SCANCODE_LSHIFT]) {
				this->midis[i]->rect.y -= 5;
			}
			else if (this->midis[i]->selected) {
				this->midis[i]->rect.y -= 5;
			}
		}
	}

	void down_key_handler() {
		for (int i=0; i < this->midis.size(); i++) {
			if (this->kmap[SDL_SCANCODE_LSHIFT]) {
				this->midis[i]->rect.y += 5;
			}
			else if (this->midis[i]->selected) {
				this->midis[i]->rect.y += 5;
			}
		}
	}

	void select_similar_midi() {
		JupiterMIDIFragment *first_midi = NULL;
		int first_midi_index = -1;
		for (int i=0; i < this->midis.size(); i++) {
			if (first_midi == NULL) {
				if (this->midis[i]->selected) {
					first_midi = this->midis[i];
					first_midi_index = i;
				}
			}
			else {
				if (this->midis[i]->midi_code == first_midi->midi_code) {
					this->midis[i]->selected = true;
				}
			}
		}

		if (first_midi != NULL) {
			for (int i=0; i < first_midi_index; i++) {
				if (this->midis[i]->midi_code == first_midi->midi_code) {
					this->midis[i]->selected = true;
				}
			}
		}
	}

	void select_midi_handler(int x, int y) {
		for (int i=0; i < this->midis.size(); i++) {
			if (this->midis[i]->is_inside(x, y)) {
				if (!this->kmap[SDL_SCANCODE_LCTRL]) {
					this->desselect_all_midis();
				}
				this->midis[i]->selected = true;
				return;
			}
		}
		this->desselect_all_midis();
		this->set_cursor_position(x);
	}

	void desselect_all_midis() {
		// fixme > separate this in 2 threads?
		for (int i=0; i < this->midis.size(); i++) {
			this->midis[i]->selected = false;
		}
	}

	void choose_midi_port() {
		// fixme > the thread is created, but is never deleted
		std::thread *t = new std::thread([&] {
			// fixme > colocar na string as opções
			// fixme > fazer validação do inteiro escolhido
			this->midi_port = get_integer_dialog("Midi Port");
		});
	}

	void update_bpm() {
		this->bpm_label->y = this->get_height() - 60;
		this->bpm_label->set_text(
			std::to_string(this->bpm) + " BPM",
			this->renderer
		);
		int line_distance = (int)(this->sec_px / (this->bpm / 60.f));
		this->bpm_lines->coords.clear();
		for (int i=this->get_start_line_pos(); i < this->get_width(); i += line_distance) {
			this->bpm_lines->coords.push_back(i);
			this->bpm_lines->coords.push_back(0);
			this->bpm_lines->coords.push_back(i);
			this->bpm_lines->coords.push_back(this->get_height());
		}
	}

	void update_sec_px_label() {
		this->sec_px_label->y = this->get_height() - 40;
		this->sec_px_label->set_text(
			std::to_string(this->sec_px) + "px/sec",
			this->renderer
		);
	}

	void update_midi() {
		for (int i=0; i < this->midis.size(); i++) {
			this->midis[i]->update(this->sec_px, this->get_start_line_pos());
		}
	}

	////// EVENTS //////
	void treat_mouse_wheel(int x_scroll) {
		std::thread thread_update_bpm(&JupiterWindow::update_bpm, this);
		std::thread thread_update_midi(&JupiterWindow::update_midi, this);
		if (this->kmap[SDL_SCANCODE_LSHIFT]) {
			x_scroll *= 4;
			int d_x = this->cursor_line->coords[0] - this->get_start_line_pos();
			this->set_start_line_to(
				this->get_start_line_pos() + x_scroll
			);
			this->set_cursor_position(this->get_start_line_pos() + d_x);
		}
		else if (this->kmap[SDL_SCANCODE_LCTRL]) {
			double cursor_seek = (this->cursor_line->coords[0] - this->get_start_line_pos()) / (float)this->sec_px;
			this->sec_px += this->sec_px_increase * x_scroll;
			if (this->sec_px <= this->min_sec_px) {
				this->sec_px = this->min_sec_px;
			}
			this->update_sec_px_label();
			this->set_cursor_position(
				this->get_start_line_pos() + (this->sec_px * cursor_seek)
			);
		}
		thread_update_bpm.join();
		thread_update_midi.join();
	}
};

int main (int argc, char** argv)
{
	JupiterWindow *window = new JupiterWindow("Jupiter");
	window->add(
		(new JupiterText(10, 10))->set_text("JUPITER 0.0.1", window->renderer)
	);
	window->add((new JupiterText(10, 30))->set_text("Space - play/pause", window->renderer));
	window->add((new JupiterText(10, 50))->set_text("p - choose MIDI port", window->renderer));
	window->add((new JupiterText(10, 70))->set_text("s - select similar midi", window->renderer));
	window->add((new JupiterText(10, 90))->set_text("up/down - move selection", window->renderer));
	window->add((new JupiterText(10, 110))->set_text("shift up/down - move everything", window->renderer));
	window->add((new JupiterText(10, 130))->set_text("c - change midi sound", window->renderer));
	window->mainloop();
	delete window;

	return EXIT_SUCCESS;
}