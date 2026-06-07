from dataclasses import dataclass

from Options import Toggle, DeathLink, Range, Choice, PerGameCommonOptions, StartInventoryPool, DefaultOnToggle


class CompletionGoal(Choice):
    """
    Select which completion goal you want for this world:
    0 = Vanilla/Beat Final Boss
    """
    display_name = "Completion Goal"
    option_vanilla = 0
    default = 0

@dataclass
class TAK2SODOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    death_link: DeathLink
    completion_goal: CompletionGoal