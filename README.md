source env/bin/activate
which pip
pip install pip-tools
pip-sync requirements.txt
make week
make pdf week=42
sudo apt install pandoc
make pdf week=42
sudo apt install texlive-xetex