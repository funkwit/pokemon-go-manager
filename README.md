# Pokemon Go Manager

Who wants to spend time managing your inventory when there are Pokemon to catch?
This Pokemon assistant helps you while you're out there playing the game legitimately.
Based on the API used in [TomTheBotter's Pokemon bot](https://github.com/TomTheBotter/Pokemon-Go-Bot-Working-Hack-API).

## USE WITH CAUTION! 

Niantic may ban you. I haven't been banned yet, but you never know.

## Features

* Automatically star Pokemon that are ready to evolve. "Ready" is when:
    * The Pokemon will evolve into a Pokemon you don't have yet, or
    * The base Pokemon in a family can evolve to its final form, or
    * Pidgey, Caterpie or Weedle can be evoled for easy XP.
* Automatically transfer Pokemon that you don't need any more. That's when:
    * It isn't the last Pokemon you have of that type (excluding evolutions), and
    * You have more than 3 of the same type of Pokemon (excluding evolutions), or
    * The Pokemon has less than half the CP of the strongest Pokemon you have of that type
* Automatically discard items that you don't want
    * Ensures that there's always a configurable buffer of empty space in your inventory
    * Retain items in configurable proportions, depending on your play style

## Future Features

* Automatically evolve Pokemon when you drop a Lucky Egg.
* Automatically heal Pokemon with potions when damaged.

## Instructions

Prerequisites: `python2.7`, `pip`, `python2.7-dev`

1. `git clone https://github.com/LukeGT/pokemon-go-manager`
2. `cd pokemon-go-manager`
3. `sudo pip install -r requirements.txt`
4. `cp credentials.example credentials.json`
5. Edit `credentials.json` to include your Google account details. If you have two-step auth, you might need to create an [App Password](https://security.google.com/settings/security/apppasswords). If you are a member of the Pokemon Trainer Club, change "provider" to "ptc".
6. `python manager.py`

Run it on a computer that's going to stay on all the time. You might want to run it in a loop, because it might crash :)

