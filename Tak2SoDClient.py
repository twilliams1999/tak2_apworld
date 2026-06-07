import asyncio
import os.path
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from enum import Enum
from enum import Flag
from typing import Callable, Optional, Any, Dict

import dolphin_memory_engine

import Utils
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, logger, \
    get_base_parser

    
class CheckTypes(Flag):
    BUGS = 1


CONNECTION_REFUSED_GAME_STATUS = "Dolphin Connection refused due to invalid Game. Please load the US Version of Tak 2 Staff of Dreams"
CONNECTION_REFUSED_SAVE_STATUS = "Dolphin Connection refused due to invalid Save. " \
                                 "Please make sure you loaded a save file used on this slot and seed."
CONNECTION_LOST_STATUS = "Dolphin Connection was lost. Please restart your emulator and make sure Tak 2 Staff of Dreams is running."
CONNECTION_CONNECTED_STATUS = "Dolphin Connected"
CONNECTION_INITIAL_STATUS = "Dolphin Connection has not been initiated"

HEALTH_ADDR = 0x81728d1c # Float
BUGS_COUNT_ADDR = 0x803c58b8 # Float


# class Bugs(Enum):


class Tak2SoDContext(CommonContext):
    command_processor = TAK2SODCommandProcessor
    game = "Tak 2: The Staff of Dreams"
    items_handling = 0b111 #full remote