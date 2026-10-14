#!/bin/sh
# Exercise installed target-native tools without changing system configuration.
set -eu

workdir=$(mktemp -d "${TMPDIR:-/tmp}/native-build-tools.XXXXXX")
trap 'rm -rf "$workdir"' EXIT HUP INT TERM
cd "$workdir"

# Kconfig includes limits.h directly. Native GCC must chain its own integer
# limits to the target libc header, rather than hiding POSIX limits.
cat > limits.c <<'EOF'
#include <limits.h>
_Static_assert(PATH_MAX > 0, "libc PATH_MAX is missing");
_Static_assert(NAME_MAX > 0, "libc NAME_MAX is missing");
_Static_assert(MB_LEN_MAX > 1, "libc multibyte limits are missing");
_Static_assert(INT_MAX == __INT_MAX__, "GCC integer limits are missing");
int main(void) { return 0; }
EOF
gcc -Wall -Wextra -Werror limits.c -o limits
./limits

flex --version
bison --version | head -n 1
bc --version | head -n 1
pahole --version

cat > parser.y <<'EOF'
%{
#include <stdio.h>
int yylex(void);
void yyerror(const char *s) { fprintf(stderr, "%s\n", s); }
%}
%token NUMBER
%%
input: NUMBER '+' NUMBER '\n' { printf("%d\n", $1 + $3); };
%%
int main(void) { return yyparse(); }
EOF
cat > scanner.l <<'EOF'
%option noyywrap noinput nounput
%{
#include <stdlib.h>
#include "parser.h"
%}
%%
[0-9]+ { yylval = atoi(yytext); return NUMBER; }
[ \t]+ ;
\n return '\n';
. return yytext[0];
%%
EOF
bison --defines=parser.h -o parser.c parser.y
flex -o scanner.c scanner.l
gcc -Wall -Wextra parser.c scanner.c -o parser
test "$(printf '19+23\n' | ./parser)" = 42
test "$(printf 'scale=3; 22/7\n' | bc)" = 3.142

cat > layout.c <<'EOF'
struct native_tools_layout { char tag; long value; int count; };
struct native_tools_layout sample;
int main(void) { return sample.count; }
EOF
gcc -g -O0 -c layout.c -o layout.o
pahole -C native_tools_layout layout.o
pahole -J layout.o
readelf -S layout.o | grep -q '\.BTF'
pahole -F btf -C native_tools_layout layout.o
printf '%s\n' 'PASS: libc/GCC limits, lexer/parser, bc arithmetic, DWARF layout and BTF encoding'
