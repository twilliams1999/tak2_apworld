import hashlib
import json
import logging
import os
import zipfile
import typing
from multiprocessing import Process

import Utils
# from BaseClasses import Item, Tutorial, ItemClassification
# from worlds.AutoWorld import World, WebWorld
# from worlds.LauncherComponents import Component, components, Type, SuffixIdentifier, icon_paths
# from worlds.Files import APPlayerContainer
# from . import Patches
# from .Events import create_events
# from .Items import item_table, NO100FItem
# from .Locations import location_table, NO100FLocation
# from .Options import NO100FOptions
# from .Regions import create_regions
# from .Rules import set_rules
# from .names import ItemNames, ConnectionNames


def run_client(ap_url=None):
    print('running Tak 2 Staff of Dreams client')
    from worlds.tak2sod.TAK2SODClient import main  # lazy import
    file_types = (('TAK2SOD Patch File', ('.aptak2sod',)), ('NGC iso', ('.gcm',)),)
    if ap_url:
        kwargs = {'patch_file': ap_url}
    else:
        kwargs = {'patch_file': Utils.open_filename("Select .aptak2sod", file_types)}
    p = Process(target=main, kwargs=kwargs)
    p.start()


components.append(
    Component("Tak 2 SoD Client",
              func=run_client,
              component_type=Type.CLIENT,
              file_identifier=SuffixIdentifier('.aptak2sod'),
              cli=True,
              icon="Tak 2 The Staff of Dreams",
              )
)
icon_paths["Tak 2 The Staff of Dreams"] = "ap:worlds.tak2sod/Assets/icon.png"

TAK2SOD_HASH = "???"


class NO100FContainer(APPlayerContainer):
    hash = TAK2SOD_HASH
    game = "Tak 2 The Staff of Dreams"
    patch_file_ending: str = ".aptak2sod"
    result_file_ending: str = ".gcm"
    zip_version: int = 1
    logger = logging.getLogger("TAK2SODPatch")

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        if 'seed' in kwargs:
            self.completion_goal: int = kwargs['completion_goal']
            self.seed: bytes = kwargs['seed']
            del kwargs['completion_goal']
            del kwargs['seed']
        super().__init__(*args, **kwargs)

    def write_contents(self, opened_zipfile: zipfile.ZipFile):
        super(TAK2SODContainer, self).write_contents(opened_zipfile)
        opened_zipfile.writestr("completion_goal",
                                self.completion_goal.to_bytes(1, "little"),
                                compress_type=zipfile.ZIP_STORED)
        opened_zipfile.writestr("zip_version",
                                self.zip_version.to_bytes(1, "little"),
                                compress_type=zipfile.ZIP_STORED)
        m = hashlib.md5()
        m.update(self.seed)
        opened_zipfile.writestr("seed",
                                m.digest(),
                                compress_type=zipfile.ZIP_STORED)

    def read_contents(self, opened_zipfile: zipfile.ZipFile) -> None:
        super(TAK2SODContainer, self).read_contents(opened_zipfile)

    @classmethod
    def get_int(cls, opened_zipfile: zipfile.ZipFile, name: str):
        if name not in opened_zipfile.namelist():
            cls.logger.warning(f"couldn't find {name} in patch file")
            return 0
        return int.from_bytes(opened_zipfile.read(name), "little")

    @classmethod
    def get_bool(cls, opened_zipfile: zipfile.ZipFile, name: str):
        if name not in opened_zipfile.namelist():
            cls.logger.warning(f"couldn't find {name} in patch file")
            return False
        return bool.from_bytes(opened_zipfile.read(name), "little")

    @classmethod
    def get_json_obj(cls, opened_zipfile: zipfile.ZipFile, name: str):
        if name not in opened_zipfile.namelist():
            cls.logger.warning(f"couldn't find {name} in patch file")
            return None
        with opened_zipfile.open(name, "r") as f:
            obj = json.load(f)
        return obj

    @classmethod
    def get_seed_hash(cls, opened_zipfile: zipfile.ZipFile):
        return opened_zipfile.read("seed")

    @classmethod
    async def apply_binary_changes(cls, opened_zipfile: zipfile.ZipFile, iso):
        cls.logger.info('--binary patching--')
        # get slot name and seed hash
        manifest = TAK2SODContainer.get_json_obj(opened_zipfile, "archipelago.json")
        slot_name = manifest["player_name"]
        slot_name_bytes = slot_name.encode('utf-8')
        slot_name_offset = 0x1e0c9c
        seed_hash = TAK2SODContainer.get_seed_hash(opened_zipfile)
        seed_hash_offset = slot_name_offset + 0x40
        # always apply these patches
        patches = [Patches.AP_SAVE_LOAD]

        with open(iso, "rb+") as stream:
            # write patches
            for patch in patches:
                cls.logger.info(f"applying patch {patches.index(patch) + 1}/{len(patches)}")
                for addr, val in patch.items():
                    stream.seek(addr, 0)
                    if isinstance(val, bytes):
                        stream.write(val)
                    else:
                        stream.write(val.to_bytes(0x4, "big"))
            # write slot name
            cls.logger.debug(f"writing slot_name to 0x{slot_name_offset:x} ({slot_name_bytes})")
            stream.seek(slot_name_offset, 0)
            stream.write(slot_name_bytes)
            cls.logger.debug(f"writing seed_hash {seed_hash} to 0x{seed_hash_offset:x}")
            stream.seek(seed_hash_offset, 0)
            stream.write(seed_hash)
        cls.logger.info('--binary patching done--')

    @classmethod
    def get_rom_path(cls) -> str:
        return get_base_rom_path()

    @classmethod
    def check_hash(cls):
        if not validate_hash():
            Exception(f"Supplied Base Rom does not match known MD5 for Tak 2 The Staff of Dreams.iso. "
                      "Get the correct game and version.")

    @classmethod
    def check_version(cls, opened_zipfile: zipfile.ZipFile) -> bool:
        version_bytes = opened_zipfile.read("zip_version")
        version = 0
        if version_bytes is not None:
            version = int.from_bytes(version_bytes, "little")
        if version != cls.zip_version:
            return False
        return True


def get_base_rom_path(file_name: str = "") -> str:
    if not file_name:
        file_name = "Tak 2 The Staff of Dreams.iso"
    if not os.path.exists(file_name):
        file_name = Utils.user_path(file_name)
    return file_name


def validate_hash(file_name: str = ""):
    file_name = get_base_rom_path(file_name)
    with open(file_name, "rb") as file:
        base_rom_bytes = bytes(file.read())
    basemd5 = hashlib.md5()
    basemd5.update(base_rom_bytes)
    return NO100F_HASH == basemd5.hexdigest()


class TAK2SODWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing the Tak 2 The Staff of Dreams Randomizer.",
        "English",
        "setup_en.md",
        "setup/en",
        ["vgm5"]
    )]


class Tak2StaffofDreamsWorld(World):
    """
    Scooby-Doo! Night of 100 Frights is a MetroidVania 3D Platformer game
    made by Heavy Iron Studios and published by THQ.

    The Mystery Gang are invited to the Mystic Manor by Holly, but shortly after arriving Scooby-Doo
    gets separated from the rest of the crew, Scooby must navigate a wide variety of levels to collect new inventions
    and scooby snacks so that he can explore new areas and look for his friends, while
    he fights off his old foes along the way.
    """
    game = "Tak 2 The Staff of Dreams"
    options_dataclass = TAK2SODOptions
    options: TAK2SODOptions
    topology_present = False

    item_name_to_id = {name: data.id for name, data in item_table.items()}
    location_name_to_id = location_table
    web = TAK2SODWeb()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snack_counter: int = 0

    def get_items(self):
        # Generate item pool
        itempool += [ItemNames.Bugs] * 100 # number of bugs

        # adjust for starting inv prog. items
        for item in self.multiworld.precollected_items[self.player]:
            if item.name in itempool and item.advancement:
                itempool.remove(item.name)

        # Convert itempool into real items
        itempool = list(map(lambda name: self.create_item(name), itempool))
        return itempool

    def create_items(self):
        self.multiworld.itempool += self.get_items()

    def get_filler_item_name(self) -> str:
        return self.random.choice(["Filler 1", "Filler 2"])

    def set_rules(self):
        create_events(self.multiworld, self.player)
        set_rules(self.multiworld, self.options, self.player)

    def create_regions(self):
        create_regions(self.multiworld, self.options, self.player)

    def fill_slot_data(self):
        return {
            "death_link": self.options.death_link.value,
            "completion_goal": self.options.completion_goal.value,
        }

    def create_item(self, name: str,) -> Item:
        item_data = item_table[name]
        classification = item_data.classification

        if name == ItemNames.Bug:
            self.bug_counter += 1
            if self.bug_counter > 100:
                classification = ItemClassification.filler

        item = TAK2SODItem(name, classification, item_data.id, self.player)

        return item

    def generate_output(self, output_directory: str) -> None:
        patch = TAK2SODContainer(path=os.path.join(output_directory,
                                f"{self.multiworld.get_out_file_name_base(self.player)}"
                                f"{TAK2SODContainer.patch_file_ending}"),
                                player=self.player,
                                player_name=self.player_name,
                                completion_goal=bool(self.options.completion_goal.value),
                                seed=self.multiworld.seed_name.encode('utf-8'),
                                )
        patch.write()