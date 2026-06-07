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


class Tak2SoDCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx: CommonContext):
        super().__init__(ctx)

    def _cmd_dolphin(self):
        """Check Dolphin Connection State"""
        if isinstance(self.ctx, Tak2SoDContext):
            logger.info(f"Dolphin Status: {self.ctx.dolphin_status}")

    def _cmd_resettak(self):
        """Force Kill Tak to escape softlocks"""
        if dolphin_memory_engine.is_hooked():
            dolphin_memory_engine.write_float(HEALTH_ADDR, 0)
            logger.info("Killing Tak :(")


class Tak2SoDContext(CommonContext):
    command_processor = TAK2SODCommandProcessor
    game = "Tak 2: The Staff of Dreams"
    items_handling = 0b111 #full remote

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.items_received_2 = []
        self.dolphin_sync_task = None
        self.dolphin_status = CONNECTION_INITIAL_STATUS
        self.awaiting_rom = False
        self.LAST_STATE = [bytes([0, 0]), bytes([0, 0]), bytes([0, 0])]
        self.last_rev_index = -1
        self.has_send_death = False
        self.forced_death = False
        self.post_boss = False
        self.last_death_link_send = time.time()
        self.current_scene_key = None
        self.use_bugs = False
        self.current_scene = None
        self.previous_scene = None

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.auth = None
        await super().disconnect(allow_autoreconnect)

    def on_package(self, cmd: str, args: dict):
        if cmd == 'Connected':
            self.current_scene_key = f"Tak2SoD_current_scene_T{self.team}_P{self.slot}"
            self.set_notify(self.current_scene_key)
            self.last_rev_index = -1
            self.items_received_2 = []
            # self.included_check_types = CheckTypes. 
            if 'bug_count' in args['slot_data']:
                self.bug_count = args['slot_data']['bug_count']
        if cmd == 'ReceivedItems':
            if args["index"] >= self.last_rev_index:
                self.last_rev_index = args["index"]
                for item in args['items']:
                    self.items_received_2.append((item, self.last_rev_index))
                    self.last_rev_index += 1
            self.items_received_2.sort(key=lambda v: v[1])

    def on_deathlink(self, data: Dict[str, Any]) -> None:
        super().on_deathlink(data)
        _give_death(self)

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            logger.info('Enter the password required to join this game:')
            self.password = await self.console_input()
        if not self.auth:
            if self.awaiting_rom:
                return
            self.awaiting_rom = True
            logger.info('Awaiting connection to Dolphin to get player information')
            return
        await self.send_connect()
    
    def run_gui(self):
        from kvui import GameManager

        class Tak2SoDManager(GameManager):
            logging_pairs = [
                ("Client", "Archipelago")
            ]
            base_title = "Archipelago Tak 2: The Staff of Dreams Client"

        self.ui = Tak2SoDManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

    # def _is_ptr_valid(ptr):
        # return (minimum address for range) <= ptr < (maximum address for range)


    def _give_bug(ctx: Tak2SoDContext, offset: int):
        cur_bug_count = dolphin_memory_engine.read_float(STORED_BUG_ADDR)
        if offset == 1:
            cur_bug_count += 5
        else:
            cur_bug_count += 1
        
        dolphin_memory_engine.write_float(STORED_BUG_ADDR, cur_bug_count)

    
    async def check_alive(ctx: Tak2SoDContext):
        cur_health = dolphin_memory_engine.read_float(HEALTH_ADDR)
        return not (cur_health <= 0 or check_control_owner(ctx, lambda owner: owner == 0))

    async def check_death(ctx: Tak2SoDContext):
        cur_health = dolphin_memory_engine.read_word(HEALTH_ADDR)

        if cur_health > 0:
            ctx.forced_death = False

        if cur_health <= 0 and not ctx.forced_death:
            if not ctx.has_send_death and time.time() >= ctx.last_death_link + 3:
                ctx.has_send_death = True
                await ctx.send_death("Tak2SoD")
        
        else:
            ctx.has_send_death = False

    async def force_death(ctx: Tak2SoDContext):
        cur_health = dolphin_memory_engine.read_float(HEALTH_ADDR)

        if cur_health == 67:
            ctx.forced_death = True
            dolphin_memory_engine.write_float(HEALTH_ADDR, 0)

    async def dolphin_sync_task(ctx: Tak2SoDContext):
        logger.info("Starting Dolphin connector. Use /dolphin for status information")
        while not ctx.exit_event.is_set():
            try:
                if dolphin_memory_engine.is_hooked() and ctx.dolphin_status == CONNECTION_CONNECTED_STATUS:
                    if not check_ingame(ctx):
                        # reset AP values when on main menu
                        
                        await asyncio.sleep(.1)
                        continue
                    if ctx.slot:
                        #if not validate_save(ctx):
                        ctx.current_scene_key = f"Tak2SoD_current_scene_T{ctx.team}_P{ctx.slot}"
                        ctx.set_notify(ctx.current_scene_key)
                        if "DeathLink" in ctx.tags:
                            await check_death(ctx)
                        await force_death(ctx)

                    else:
                        if not ctx.auth:
                            ctx.auth = dolphin_memory_engine.read_bytes(SLOT_NAME_ADDR, 0x40).decode('utf-8').strip(
                                '\0')
                            if ctx.auth == '\x02\x00\x00\x00\x04\x00\x00\x00\x02\x00\x00\x00\x04\x00\x00\x00\x02\x00\x00' \
                                       '\x00\x02\x00\x00\x00\x04\x00\x00\x00\x04':
                                logger.info("Vanilla game detected. Please load the patched game.")
                                ctx.dolphin_status = CONNECTION_REFUSED_GAME_STATUS
                                ctx.awaiting_rom = False
                                dolphin_memory_engine.un_hook()
                                await ctx.disconnect()
                                await asyncio.sleep(5)
                        if ctx.awaiting_rom:
                            await ctx.server_auth()
                    await asyncio.sleep(.5)
                else:
                    if ctx.dolphin_status == CONNECTION_CONNECTED_STATUS:
                        logger.info("Connection to Dolphin lost, reconnecting...")
                        ctx.dolphin_status = CONNECTION_LOST_STATUS
                    logger.info("Connection to Dolphin lost, reconnecting...")
                    dolphin_memory_engine.hook()
                    if dolphin_memory_engine.is_hooked():
                        if dolphin_memory_engine.read_bytes(0x80000000, 6) == b'GIHE78':
                            logger.info(CONNECTION_CONNECTED_STATUS)
                            ctx.dolphin_status = CONNECTION_CONNECTED_STATUS
                            ctx.locations_checked = set()
                        else:
                            logger.info(CONNECTION_REFUSED_GAME_STATUS)
                            ctx.dolphin_status = CONNECTION_REFUSED_GAME_STATUS
                            dolphin_memory_engine.un_hook()
                            await asyncio.sleep(1)
                    else:
                        logger.info("Connection to Dolphin failed, attempting again in 5 seconds...")
                        ctx.dolphin_status = CONNECTION_LOST_STATUS
                        await ctx.disconnect()
                        await asyncio.sleep(5)
                        continue
            except Exception:
                dolphin_memory_engine.un_hook()
                logger.info("Connection to Dolphin failed, attempting again in 5 seconds...")
                logger.error(traceback.format_exc())
                ctx.dolphin_status = CONNECTION_LOST_STATUS
                await ctx.disconnect()
                await asyncio.sleep(5)
                continue


async def patch_and_run_game(ctx: Tak2SoDContext, patch_file):
    try:
        result_path = os.path.splitext(patch_file)[0] + Tak2SoDContainer.result_file_ending
        with zipfile.ZipFile(patch_file, 'r') as patch_archive:
            if not Tak2SoDContainer.check_version(patch_archive):
                logger.error(
                    "apTak2SoD version doesn't match this client. Make sure your generator and client are the same")
                raise Exception("apTak2SoD version doesn't match this client.")

            #check hash
            Tak2SoDContainer.check_hash()

            shutil.copy(Tak2SoDContainer.get_rom_path(), result_path)
            await Tak2SoDContainer.apply_binary_changes(zipfile.ZipFile(patch_file, 'r'), result_path)

            logger.info('--patching success--')
            if sys.platform == "win32":
                os.startfile(result_path)
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.call([opener, result_path])
            
    except Exception as msg:
        logger.info(msg, extra={'compact_gui': True})
        logger.debug(traceback.format_exc())
        ctx.gui_error('Error',msg)
    
def main(connect=None, password=None, patch_file=None):
    # Text Mode to use !hint and such with games that no text entry
    Utils.init_logging("Tak2SoDClient")

    async def _main(connect, password, patch_file):
        ctx = Tak2SoDContext(connect, password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        ctx.patch_task = None
        if patch_file:
            ext = os.path.splitext(patch_file)[1]
            if ext == Tak2SoDContainer.patch_file_ending:
                logger.info("apTak2SoD file supplied, beginning patching process...")
                ctx.patch_task = asyncio.create_task(patch_and_run_game(ctx, patch_file), name="PatchGame")
            elif ext == Tak2SoDContainer.result_file_ending:
                if sys.platform == "win32":
                    os.startfile(patch_file)
                else:
                    opener = "open" if sys.platform == "darwin" else "xdg-open"
                    subprocess.call([opener, patch_file])
            else:
                logger.warning(f"Unknown patch file extention {ext}")

        if ctx.patch_task:
            await ctx.patch_task
        
        await asyncio.sleep(1)

        ctx.dolphin_sync_task = asyncio.create_task(dolphin_sync_task(ctx), name="DolphinSync")

        await ctx.exit_event.wait()
        ctx.server_address = None

        await ctx.shutdown()

        if ctx.dolphin_sync_task:
            await asyncio.sleep(3)
            await ctx.dolphin_sync_task

    import colorama

    colorama.init()
    asyncio.run(_main(connect, password, patch_file))
    colorama.deinit()

if __name__ == '__main__':
    parser = get_base_parser()
    parser.add_argument('patch_file', default="", type=str, nargs="?",
                        help='Path to an .aptak2sod patch file')
    args = parser.parse_args()
    main(args.connect, args.password, args.patch_file)
                    

            