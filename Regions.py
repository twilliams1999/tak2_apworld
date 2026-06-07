from typing import List, Dict

from . import TAK2SODOptions
from .Locations import TAK2SODLocation, location_table
from .names import ConnectionNames, LevelNames, RegionNames, LocationNames

from BaseClasses import MultiWorld, Region, Entrance


def create_region(multiworld: MultiWorld, player: int, name: str, locations=None, exits=None) -> Region:
    ret = Region(name, player, multiworld)
    if locations:
        for location in locations:
            loc_id = location_table[location]
            location = TAK2SODLocation(player, location, loc_id, ret)
            ret.locations.append(location)

    if exits:
        for _exit in exits:
            ret.exits.append(Entrance(player, _exit, ret))
    return ret

exit_table: Dict[str, List[str]] = {

    RegionNames.menu: [ConnectionNames.start_game]
}


def create_regions(world: MultiWorld, options: TAK2SODOptions, player: int):
    # create regions
    world.regions += [
        create_region(world, player, k, _get_locations_for_region(options, k), v) for k, v in exit_table.items()
    ]

    # connect regions
    world.get_entrance(ConnectionNames.start_game, player).connect(world.get_region(RegionNames.hub1, player))
    for k, v in exit_table.items():
        if k == RegionNames.menu:
            continue
        for _exit in v:
            exit_regions = _exit.split('->')
            assert len(exit_regions) == 2
            target = world.get_region(exit_regions[1], player)
            world.get_entrance(_exit, player).connect(target)