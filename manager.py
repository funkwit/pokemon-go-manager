import json
import logging
import random
from collections import defaultdict
from time import sleep

from pgoapi import PGoApi


# Load configuration parameters
class CONFIG(object): pass
for key, value in json.load(open('params.json')).iteritems():
  setattr(CONFIG, key, value)

POKEBALL_FAMILY = 0
POTION_FAMILY = 1
REVIVE_FAMILY = 2
BERRY_FAMILY = 7

TOTAL_PROPORTION = CONFIG.POKEBALL_PROPORTION + CONFIG.BERRY_PROPORTION + CONFIG.POTION_PROPORTION + CONFIG.REVIVE_PROPORTION
ITEM_FAMILY_RATIOS = {
  POKEBALL_FAMILY: CONFIG.POKEBALL_PROPORTION/TOTAL_PROPORTION,
  POTION_FAMILY: CONFIG.POTION_PROPORTION/TOTAL_PROPORTION,
  REVIVE_FAMILY: CONFIG.REVIVE_PROPORTION/TOTAL_PROPORTION,
  BERRY_FAMILY: CONFIG.BERRY_PROPORTION/TOTAL_PROPORTION,
}


# Load resources
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

def get_item_family(item_id):
  return (item_id-1)/100


def setup_logging():
  logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(module)10s] [%(levelname)5s] %(message)s')
  logging.getLogger('requests').setLevel(logging.INFO)
  logging.getLogger('pgoapi').setLevel(logging.INFO)
  logging.getLogger('rpc_api').setLevel(logging.INFO)


def main():

  setup_logging()
  api = PGoApi()

  api.set_position(*CONFIG.STARTING_POSITION)

  while not api.login(**credentials):
    sleep(2)

  while True:
    clean_up_inventory(api)
    sleep(CONFIG.CLEANUP_POLL_TIME + random.uniform(-1, 1) * CONFIG.POLL_JITTER)


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

  player_data = api.get_player()['responses']['GET_PLAYER']['player_data']

  # Grab the inventory response and fill some data structures with required information
  response = api.get_inventory()['responses']['GET_INVENTORY']
  inventory_items = response['inventory_delta']['inventory_items']
  caught_pokemon = defaultdict(list)
  candies = defaultdict(int)
  pokemon_by_id = dict()
  item_counts = dict()

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

    elif 'candy' in data:
      # Is candy
      family = data['candy']
      candies[family['family_id']] += family.get('candy', 0)

    elif 'item' in data:
      # It's an item
      item = data['item']
      item_counts[item['item_id']] = item.get('count', 0)

    else:
      # Ignore
      pass

  # Sort caught pokemon by CP
  for pokemon_id in caught_pokemon:
    caught_pokemon[pokemon_id].sort(key=lambda p: p['cp'], reverse=True)

  # Count items
  item_counts[801] = 1 # You always have 1 camera, but it doesn't show up
  total_items = 0
  item_family_counts = defaultdict(int)
  for item_id, count in item_counts.iteritems():
    total_items += count
    item_family_counts[get_item_family(item_id)] += count

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
    if family_id in CONFIG.EASY_EVOLUTIONS:
      candy_req = candy_map[family_id]
      for pokemon in caught_pokemon[family_id]:
        if pokemon['id'] in to_evolve: continue
        if candy_req > candies[family_id]: break
        to_evolve.add(pokemon['id'])
        candies[family_id] -= candy_req

  # Count pending evolutions per pokemon type
  evolution_counts = defaultdict(int)
  for id in to_evolve:
    pokemon = pokemon_by_id[id]
    evolution_counts[pokemon['pokemon_id']] += 1

  # Drop unncecessary items
  if CONFIG.ENABLE_DISCARD_ITEMS:

    to_discard =  total_items + CONFIG.ITEM_BUFFER - player_data['max_item_storage']
    if to_discard > 0:

      # Calculate which items are in excess based on ideal ratios
      undiscardable_count = total_items - sum( item_family_counts[id] for id in ITEM_FAMILY_RATIOS )
      ideal_count = player_data['max_item_storage'] - CONFIG.ITEM_BUFFER - undiscardable_count
      ideals = { id: ratio * ideal_count for id, ratio in ITEM_FAMILY_RATIOS.iteritems() }
      excess = { id: item_family_counts[id] - ideals[id] for id in ITEM_FAMILY_RATIOS if item_family_counts[id] - ideals[id] > 0 }
      excess_total = sum( count for id, count in excess.iteritems() )
      discard_counts = { id: int(0.5 + count/excess_total*to_discard) for id, count in excess.iteritems() }

      # Perform discards, starting with worst items first
      for id, discard_count in discard_counts.iteritems():
        item_id = id*100 + 1
        while discard_count > 0:
          current_count = min(discard_count, item_counts[item_id])
          api.log.info('Discarding %s of item %s' % (current_count, item_id))
          if not CONFIG.DRY_RUN:
            api.recycle_inventory_item(item_id=item_id, count=current_count)
            sleep(2)
          discard_count -= current_count
          item_id += 1


  # Assign favourites accordingly
  if CONFIG.ENABLE_STAR_EVOLUTIONS:
    for id, pokemon in pokemon_by_id.iteritems():
      should_evolve = (id in to_evolve)
      if should_evolve != ('favorite' in pokemon):
        api.log.info('Favourite = %s, %s (CP %s)' % (should_evolve, pokemon_names[pokemon['pokemon_id']], pokemon['cp']))
        if not CONFIG.DRY_RUN:
          api.set_favorite_pokemon(pokemon_id=id, is_favorite=should_evolve)
          sleep(2)

  if CONFIG.ENABLE_TRANSFER_POKEMON:
    # Turn low CP pokemon into candy, and keep no more than MAX_SIMILAR_POKEMON of each type
    for id, pokemons in caught_pokemon.iteritems():
      if len(pokemons) == 0: continue
      max_cp = pokemons[0]['cp']
      cp_threshold = max_cp * CONFIG.CP_THRESHOLD_FACTOR
      max_pokemon = CONFIG.MAX_SIMILAR_POKEMON + evolution_counts[id]
      min_pokemon = CONFIG.MIN_SIMILAR_POKEMON + evolution_counts[id]

      for index, pokemon in enumerate(pokemons):
        if pokemon['id'] in to_evolve or index < min_pokemon: continue
        if pokemon['cp'] < cp_threshold or index >= max_pokemon:
          api.log.info('Grinding up %s (CP %s)' % (pokemon_names[pokemon['pokemon_id']], pokemon['cp']))
          if not CONFIG.DRY_RUN:
            api.release_pokemon(pokemon_id=pokemon['id'])
            sleep(2)

  
if __name__ == '__main__':
  main()
