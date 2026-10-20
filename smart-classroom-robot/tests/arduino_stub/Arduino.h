/* Minimal Arduino stubs so classroom_robot.ino can be compiled and RUN on a PC.
   Not a simulator of the AVR - just enough of the API to exercise the sketch's
   command parser, angle clamping and movement logic without hardware. */
#pragma once
#include <string>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <algorithm>
#include <deque>
#include <cctype>

#define HIGH 1
#define LOW 0
#define OUTPUT 1
#define INPUT 0
#define F(x) (x)
#define PROGMEM

using std::abs;

// ------------------------------------------------------------ Arduino String
class String {
 public:
  std::string s;
  String() {}
  String(const char *c) : s(c ? c : "") {}
  String(const std::string &c) : s(c) {}

  int length() const { return (int)s.size(); }
  void trim() {
    size_t b = s.find_first_not_of(" \t\r\n");
    size_t e = s.find_last_not_of(" \t\r\n");
    s = (b == std::string::npos) ? "" : s.substr(b, e - b + 1);
  }
  void toUpperCase() {
    for (auto &c : s) c = (char)std::toupper((unsigned char)c);
  }
  int indexOf(char c) const {
    size_t p = s.find(c);
    return p == std::string::npos ? -1 : (int)p;
  }
  String substring(int from) const { return String(s.substr((size_t)from)); }
  String substring(int from, int to) const {
    return String(s.substr((size_t)from, (size_t)(to - from)));
  }
  bool equals(const char *o) const { return s == std::string(o ? o : ""); }
  int toInt() const { return std::atoi(s.c_str()); }
  const char *c_str() const { return s.c_str(); }

  bool operator==(const char *o) const { return s == std::string(o ? o : ""); }
  bool operator==(const String &o) const { return s == o.s; }
  String &operator+=(char c) { s += c; return *this; }
};

// ------------------------------------------------------------------- Serial
class SerialClass {
 public:
  std::deque<char> rx;          // what the "PC" has sent to the board
  std::string tx;               // everything the board printed
  bool echo = true;             // mirror to stdout (off in REPL mode)

  void begin(long) {}
  int available() { return (int)rx.size(); }
  int read() {
    if (rx.empty()) return -1;
    char c = rx.front(); rx.pop_front(); return c;
  }
  void feed(const std::string &line) { for (char c : line) rx.push_back(c); }

  void print(const char *v)   { tx += v; if (echo) std::fputs(v, stdout); }
  void print(const String &v) { print(v.c_str()); }
  void print(char v)          { char b[2] = {v, 0}; print(b); }
  void print(int v)           { char b[16]; std::snprintf(b, sizeof b, "%d", v); print(b); }
  void print(unsigned v)      { print((int)v); }
  void println()              { print("\n"); }
  void println(const char *v) { print(v); print("\n"); }
  void println(const String &v) { print(v.c_str()); print("\n"); }
  void println(int v)         { print(v); print("\n"); }
  void println(unsigned v)    { print((int)v); print("\n"); }
};
extern SerialClass Serial;

// ------------------------------------------------------------------- timing
extern unsigned long g_millis;
inline void delay(unsigned long ms) { g_millis += ms; }
inline unsigned long millis() { return g_millis; }

// -------------------------------------------------------------------- gpio
extern int g_pins[64];
inline void pinMode(uint8_t, uint8_t) {}
inline void digitalWrite(uint8_t pin, uint8_t v) { if (pin < 64) g_pins[pin] = v; }
inline void tone(uint8_t, unsigned, unsigned) {}
inline void noTone(uint8_t) {}
