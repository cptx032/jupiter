#include <math.h>
#include <string>
#include <iostream>
#include <thread>
#include <SDL2/SDL.h>
#include <SDL2/SDL_ttf.h>
#include <vector>
#include "RtMidi.h"


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
	bool visible;
	bool filled;

	JupiterRectangle(int x, int y, int width, int height, int color) {
		this->visible = true;
		this->filled = false;

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

	RtMidiIn *midi_in;


	JupiterWindow(const char* title) {
		// initializing kmap
		for (int i=0; i < 1024; i++) {
			this->kmap[i] = false;
		}

		this->clear_color = 0x333333;
		SDL_Init(SDL_INIT_EVERYTHING);
		TTF_Init();
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

		this->midi_in = new RtMidiIn(
			RtMidi::Api::LINUX_ALSA,
			"Jupiter"
		);
		std::cout << "MIDI PORTS: " << this->midi_in->getPortCount() << std::endl;
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
		SDL_DestroyWindow(this->window);
		SDL_Quit();
		delete this->midi_in;
		delete this->start_line;
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

	void draw() {
		if (this->playing) {
			float duration = (SDL_GetTicks() - this->start_play) / 1000.f;
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
		}
		this->clear();
		for (int i=0; i < this->draws.size(); i++) {
			this->draws[i]->draw(this->renderer);
		}
		SDL_RenderPresent(this->renderer);
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
						}
						else {
							this->play_line->visible = true;
							this->play_position_label->visible = true;
							this->start_play = SDL_GetTicks();
							this->start_seek = (this->cursor_line->coords[0] - this->get_start_line_pos()) / (float)this->sec_px;
						}
						this->playing = !this->playing;
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
						this->set_cursor_position(event.button.x);
					}
				}
			}
			this->draw();
		}
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

	////// EVENTS //////
	void treat_mouse_wheel(int x_scroll) {
		std::thread t(&JupiterWindow::update_bpm, this);
		if (this->kmap[SDL_SCANCODE_LSHIFT]) {
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
		t.join();
	}
};

int main (int argc, char** argv)
{
	JupiterWindow *window = new JupiterWindow("Jupiter");
	window->add(
		(new JupiterText(10, 10))->set_text("JUPITER 0.0.1", window->renderer)
	);
	window->mainloop();
	delete window;
	return EXIT_SUCCESS;
}