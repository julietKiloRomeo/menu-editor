
default: help

help:
	@echo "usage: make [pdf | week | recipe]"

week:
	@echo "This week is:"
	@date +%V

dry:
	@env/bin/python parser.py menu $(week)

pdf:
	@env/bin/python parser.py menu $(week) > shopping.md
	@pandoc shopping.md -f gfm -H chapter_break.tex -V geometry:a4paper -V geometry:margin=4cm -V mainfont="Montserrat" -V monofont="DejaVu Sans Mono" --pdf-engine=xelatex -o shopping.pdf
	@xdg-open shopping.pdf &

recipe:
	@env/bin/python editor.py recipe edit $(name)

