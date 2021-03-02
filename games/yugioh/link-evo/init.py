# init.py
#
# descr: adds a symlink to the save dir of this repo
#
# prereqs: operating system is windows
#          symlinks enabled for non admin users (enable windows developer mode) or run script as admin
#
# todos: handle when symlinks cant be created or the dir does not exist

import os
import shutil
import re

dir_save_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'save')
dir_steam_userdata = r'C:\Program Files (x86)\Steam\userdata'
dir_rel_game_id = r'1150640\remote'

dirs_game_id = []
dirs_save = []

assert(os.path.isdir(dir_steam_userdata))

pattern = dir_steam_userdata + r".*" + dir_rel_game_id
pattern = pattern.replace('\\', '\\\\').replace('(', '\(').replace(')', '\)') # TODO: bad practice

for path, dirs, files in os.walk(dir_steam_userdata, followlinks=True):
    matches = re.finditer(pattern, path)
    for m in matches:
        dirs_save.append(m.group(0))

assert(all([True for d in dirs_save if os.path.isdir(d)]))
assert(len(dirs_save) == 1)

dir_save = dirs_save[0]

assert(os.path.isdir(dir_save))

if os.path.islink(dir_save):
    print("INFO: dir '" + str(dir_save) + "' is a symlink already")
    exit
else:
    print("PROMPT: replace '" + str(dir_save) + "' with a symlink to '" + str(dir_save_repo) + "'? (y/n)")
    while True:
        choice = input().lower()
        if choice == 'yes' or choice == 'y':
            shutil.rmtree(dir_save, ignore_errors=True)
            os.symlink(dir_save_repo, dir_save)
            print("INFO: replaced '" + str(dir_save) + "' with a symlink to '" + str(dir_save_repo) + "'")
            break
        elif choice == 'no' or choice == 'n':
            print("INFO: skipped alteration of '" + str(dir_save) + "'")
            break
        else:
            print("ERROR: respond with yes/no")


