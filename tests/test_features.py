import asyncio
import importlib
import sys
import types
import unittest


def load_plugin_module():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event_module = types.ModuleType("astrbot.api.event")
    star_module = types.ModuleType("astrbot.api.star")

    class DummyFilter:
        @staticmethod
        def command(_name):
            return lambda function: function

    class DummyEventType:
        pass

    class DummyContext:
        pass

    class DummyStar:
        def __init__(self, _context):
            pass

    class DummyLogger:
        @staticmethod
        def info(_message):
            pass

    event_module.filter = DummyFilter
    event_module.AstrMessageEvent = DummyEventType
    star_module.Context = DummyContext
    star_module.Star = DummyStar
    api.logger = DummyLogger
    astrbot.api = api

    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
    sys.modules["astrbot.api.event"] = event_module
    sys.modules["astrbot.api.star"] = star_module

    return importlib.import_module("main")


plugin_module = load_plugin_module()


class DummyEvent:
    def __init__(self, message):
        self.message_str = message

    @staticmethod
    def plain_result(message):
        return message


def run_command(command):
    async def collect():
        return [message async for message in command]

    return asyncio.run(collect())


class PluginFeatureTests(unittest.TestCase):
    def setUp(self):
        self.plugin = plugin_module.LobFullEgoPlugin.__new__(
            plugin_module.LobFullEgoPlugin)
        self.plugin.weapon_lib = {
            "训练剑": {"dmg_type": "物理", "speed": "快", "level": "HE"},
            "精神枪": {"dmg_type": "精神", "speed": "快", "level": "HE"}
        }
        self.plugin.armor_lib = {
            "训练服": {
                "level": "HE", "phy": 1.0, "spi": 1.0,
                "cor": 1.0, "sou": 1.0
            }
        }
        self.plugin.trinket_lib = {}
        self.plugin.monster_lib = {}
        self.plugin.staff_data = {}
        self.plugin.cd_data = {}
        self.plugin.attack_stack = {}
        self.plugin.dodge_queue = {}
        self.plugin.dying_queue = {}
        self.plugin.raid_status = {}
        self.plugin._save_all = lambda: None

    @staticmethod
    def make_staff(weapon="训练剑", hp=6.0, crazy=False, dead=False):
        return {
            "weapon": weapon,
            "armor": "训练服",
            "trinkets": [],
            "max_trinket_slot": 3,
            "hp": hp,
            "is_dying": dead,
            "is_crazy": crazy,
            "crazy_value": 6.0 if crazy else 0,
            "is_dead": dead
        }

    def test_suppress_monster_and_clear_pending_actions(self):
        self.plugin.monster_lib["测试异想体"] = {
            "level": "HE", "q_counter": 0, "q_counter_max": 3
        }
        self.plugin.raid_status["测试异想体"] = {"is_raid": True, "hp": 4.0}
        self.plugin.cd_data["甲_测试异想体"] = 100
        self.plugin.attack_stack["甲_测试异想体"] = 2
        self.plugin.dodge_queue["乙"] = {"source_monster": "测试异想体"}

        messages = run_command(
            self.plugin.cmd_suppress(DummyEvent(".镇压 测试异想体")))

        self.assertIn("已被立即镇压", messages[0])
        self.assertFalse(self.plugin.raid_status["测试异想体"]["is_raid"])
        self.assertEqual(self.plugin.raid_status["测试异想体"]["hp"], 0)
        self.assertEqual(self.plugin.monster_lib["测试异想体"]["q_counter"], 3)
        self.assertEqual(self.plugin.cd_data, {})
        self.assertEqual(self.plugin.attack_stack, {})
        self.assertEqual(self.plugin.dodge_queue, {})

    def test_kill_staff_marks_permanent_death_and_clears_queues(self):
        self.plugin.staff_data["甲"] = self.make_staff(crazy=True)
        self.plugin.dying_queue["甲"] = {"expire": 9999999999}
        self.plugin.dodge_queue["甲"] = {"source_monster": "测试异想体"}
        self.plugin.cd_data["甲_测试异想体"] = 100
        self.plugin.attack_stack["甲_测试异想体"] = 2

        messages = run_command(
            self.plugin.cmd_kill_staff(DummyEvent(".彻底杀死 甲")))

        staff = self.plugin.staff_data["甲"]
        self.assertIn("已被彻底杀死", messages[0])
        self.assertEqual(staff["hp"], 0)
        self.assertTrue(staff["is_dying"])
        self.assertTrue(staff["is_dead"])
        self.assertFalse(staff["is_crazy"])
        self.assertNotIn("甲", self.plugin.dying_queue)
        self.assertNotIn("甲", self.plugin.dodge_queue)
        self.assertEqual(self.plugin.cd_data, {})
        self.assertEqual(self.plugin.attack_stack, {})

    def test_normal_staff_can_fight_each_other(self):
        self.plugin.staff_data["甲"] = self.make_staff()
        self.plugin.staff_data["乙"] = self.make_staff()

        messages = run_command(self.plugin.cmd_staff_fight(
            DummyEvent(".员工互殴 甲 对 乙 进行 2次攻击，此攻击加成为 0")))

        self.assertIn("甲 攻击员工 乙", messages[0])
        self.assertEqual(self.plugin.staff_data["乙"]["hp"], 4.0)

    def test_crazy_attacker_can_attack_normal_staff(self):
        self.plugin.staff_data["甲"] = self.make_staff(crazy=True)
        self.plugin.staff_data["乙"] = self.make_staff()

        messages = run_command(self.plugin.cmd_attack_crazy(
            DummyEvent(".攻击疯狂 甲 对 乙 进行 1次攻击，此攻击加成为 0")))

        self.assertIn("甲 攻击员工 乙", messages[0])
        self.assertEqual(self.plugin.staff_data["乙"]["hp"], 5.0)

    def test_mental_weapon_calms_crazy_target_without_hp_damage(self):
        self.plugin.staff_data["甲"] = self.make_staff(weapon="精神枪")
        self.plugin.staff_data["乙"] = self.make_staff(crazy=True)
        self.plugin.staff_data["乙"]["crazy_value"] = 1.0

        messages = run_command(self.plugin.cmd_attack_crazy(
            DummyEvent(".攻击疯狂 甲 对 乙 进行 1次攻击，此攻击加成为 0")))

        target = self.plugin.staff_data["乙"]
        self.assertIn("已解除疯狂状态", messages[0])
        self.assertEqual(target["hp"], 6.0)
        self.assertFalse(target["is_crazy"])
        self.assertEqual(target["crazy_value"], 0)

    def test_staff_fight_moves_zero_hp_target_to_dying_queue(self):
        self.plugin.staff_data["甲"] = self.make_staff()
        self.plugin.staff_data["乙"] = self.make_staff(hp=1.0)

        messages = run_command(self.plugin.cmd_staff_fight(
            DummyEvent(".员工互殴 甲 对 乙 进行 1次攻击，此攻击加成为 0")))

        target = self.plugin.staff_data["乙"]
        self.assertIn("陷入濒死状态", messages[0])
        self.assertEqual(target["hp"], 0)
        self.assertTrue(target["is_dying"])
        self.assertIn("乙", self.plugin.dying_queue)

    def test_dead_staff_error_paths_do_not_reference_missing_names(self):
        self.plugin.staff_data["甲"] = self.make_staff(dead=True)
        self.plugin.staff_data["乙"] = self.make_staff(crazy=True)

        crazy_messages = run_command(
            self.plugin.cmd_go_crazy(DummyEvent(".陷入疯狂 甲")))
        rest_messages = run_command(
            self.plugin.cmd_rest(DummyEvent(".休息 甲")))
        attack_messages = run_command(self.plugin.cmd_attack_crazy(
            DummyEvent(".攻击疯狂 甲 对 乙 进行 1次攻击，此攻击加成为 0")))

        self.assertTrue(all("甲" in message for message in (
            crazy_messages[0], rest_messages[0], attack_messages[0])))


if __name__ == "__main__":
    unittest.main()
