import json
import logging
import random
from collections import defaultdict
from time import sleep

from pgoapi import PGoApi


CLEANUP_POLL_TIME = 60
POLL_JITTER = 20
CP_THRESHOLD_FACTOR = 0.5
MAX_SIMILAR_POKEMON = 3
MIN_SIMILAR_POKEMON = 1

EASY_EVOLUTIONS = [ 10, 13, 16 ]


credentials = json.load(open('credentials.json'))
pokemon_names = { int(key): value for key, value in json.load(open('name_id.json')).iteritems() }
candy_map = { int(key): value for key, value in json.load(open('candy_map.json')).iteritems() }

front_evo_map = defaultdict(list)
back_evo_map = dict()

for key, value in json.load(open('evo_map.json')).iteritems():
  front_evo_map[value].append(int(key))
  back_evo_map[int(key)] = value


def get_all_evos(id):
  if id in front_evo_map:
    ret = [ id ]
    for evo in front_evo_map[id]:
      ret += get_all_evos(evo)
    return ret
  else:
    return [ id ]


def candy_for_final(id):
  if id in candy_map:
    return candy_map[id] + candy_for_final(front_evo_map[id][0])
  else:
    return 0


def setup_logging():
  logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(module)10s] [%(levelname)5s] %(message)s')
  logging.getLogger('requests').setLevel(logging.INFO)
  logging.getLogger('pgoapi').setLevel(logging.INFO)
  logging.getLogger('rpc_api').setLevel(logging.INFO)


def main():

  setup_logging()
  api = PGoApi({}, pokemon_names)

  while not api.login(**credentials):
    pass

  while True:
    clean_up_inventory(api)
    sleep(CLEANUP_POLL_TIME + random.uniform(-1, 1) * POLL_JITTER)


def clean_up_inventory(api):
  """
  - Stars pokemon which are ready to evolve
    - Stars a pokemon when you haven't got its evolution yet
    - If you have all of a pokemon's evolutions, then wait until you can evolve the first pokemon to the last evolution
    - If the pokemon is an "EASY_EVOLUTION", then star when the first evolution is ready
  - Transfers weakest pokemon by CP
    - Measures weakness based on highest CP Pokemon
    - Limits maximum amount of similar pokemon
  """

  response = api.get_inventory().call()['responses']['GET_INVENTORY']
  inventory_items = response['inventory_delta']['inventory_items']
  caught_pokemon = defaultdict(list)
  candies = defaultdict(int)
  pokemon_by_id = dict()

  for inventory_item in inventory_items:
    data = inventory_item['inventory_item_data']

    if 'pokemon_data' in data:
      # Is pokemon
      pokemon = data['pokemon_data']
      if 'cp' in pokemon:
        caught_pokemon[pokemon['pokemon_id']].append(pokemon)
        pokemon_by_id[pokemon['id']] = pokemon
      else:
        # It's an egg
        pass

    elif 'pokemon_family' in data:
      # Is candy
      family = data['pokemon_family']
      candies[family['family_id']] += family.get('candy', 0)

    else:
      # Ignore
      pass

  for pokemon_id in caught_pokemon:
    caught_pokemon[pokemon_id].sort(key=lambda p: p['cp'], reverse=True)

  to_evolve = set()

  # Star pokemon that should be evolved into new evolutions
  for family_id in candies:

    # If we're missing the evolution and we have enough candy to get there,
    # mark the pokemon with the highest CP for evolution.
    for evo in get_all_evos(family_id):

      if evo in caught_pokemon: continue

      pre = back_evo_map.get(evo)
      if pre in caught_pokemon and candy_map[pre] <= candies[family_id]:
        for pokemon in caught_pokemon[pre]:
          if pokemon['id'] not in to_evolve:
            to_evolve.add(pokemon['id'])
            candies[family_id] -= candy_map[pre]
            break

    # Star base pokemon which can evolve to their final form
    if family_id in candy_map:
      candy_req = candy_for_final(family_id)
      for pokemon in caught_pokemon[family_id]:
        if pokemon['id'] in to_evolve: continue
        if candy_req > candies[family_id]: break
        to_evolve.add(pokemon['id'])
        candies[family_id] -= candy_req
  
    # Star pokemon that should be farmed for evolution XP
    if family_id in EASY_EVOLUTIONS:
      candy_req = candy_map[family_id]
      for pokemon in caught_pokemon[family_id]:
        if pokemon['id'] in to_evolve: continue
        if candy_req > candies[family_id]: break
        to_evolve.add(pokemon['id'])
        candies[family_id] -= candy_req
  
  evolution_counts = defaultdict(int)

  api.log.info('To evolve:')
  for id in to_evolve:
    pokemon = pokemon_by_id[id]
    evolution_counts[pokemon['pokemon_id']] += 1
    api.log.info('%s (CP %s)' % (pokemon_names[pokemon['pokemon_id']], pokemon['cp']))

  # Assign favourites accordingly
  for id, pokemon in pokemon_by_id.iteritems():
    if (id in to_evolve) != ('favorite' in pokemon):
      api.set_favorite_pokemon(pokemon_id=id, is_favorite=(id in to_evolve)).call()

  # Turn low CP pokemon into candy, and keep no more than MAX_SIMILAR_POKEMON of each type
  for id, pokemons in caught_pokemon.iteritems():
    if len(pokemons) == 0: continue
    max_cp = pokemons[0]['cp']
    cp_threshold = max_cp * CP_THRESHOLD_FACTOR
    max_pokemon = MAX_SIMILAR_POKEMON + evolution_counts[id]
    min_pokemon = MIN_SIMILAR_POKEMON + evolution_counts[id]

    for index, pokemon in enumerate(pokemons):
      if pokemon['id'] in to_evolve or index < min_pokemon: continue
      if pokemon['cp'] < cp_threshold or index >= max_pokemon:
        api.log.info('Grinding up %s (CP %s)' % (pokemon_names[pokemon['pokemon_id']], pokemon['cp']))
        api.release_pokemon(pokemon_id=pokemon['id']).call()

  
if __name__ == '__main__':
  main()
