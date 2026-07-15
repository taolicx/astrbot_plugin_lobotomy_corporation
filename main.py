import json
import time
import os
from pathlib import Path
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger


# ===================== 全局常量配置 =====================
LEVEL_WEIGHT = {"ALEPH": 3, "WAW": 2, "HE": 1}
SPEED_CD_MAP = {
    "极快": 20 * 60,   # 20分钟
    "快": 20 * 60,     # 20分钟
    "一般": 40 * 60,   # 40分钟
    "慢": 60 * 60,     # 60分钟
    "极慢": 60 * 60    # 60分钟
}
ARMOR_HP_BASE = {"ALEPH": 8.0, "WAW": 7.0, "HE": 6.0}
MONSTER_HP_BASE = {"ALEPH": 8.0, "WAW": 6.0, "HE": 4.0}
DEFAULT_TRINKET_SLOT = 3
REST_HP_RECOVER = 2.0
REST_CD_EXTEND = 30 * 60
DODGE_EXPIRE = 60 * 60
DYING_RESCUE_EXPIRE = 60 * 60
VALID_TRINKET_PROP = ["hp", "sp", "atk", "spd", "succ"]

SAVE_WEAPON = "weapon_lib.json"
SAVE_ARMOR = "armor_lib.json"
SAVE_TRINKET = "trinket_lib.json"
SAVE_MONSTER = "monster_lib.json"
SAVE_STAFF = "staff_data.json"
SAVE_COOLDOWN = "attack_cd.json"
SAVE_ATTACK_STACK = "attack_stack.json"
SAVE_DODGE_QUEUE = "dodge_wait.json"
SAVE_DYING_QUEUE = "dying_staff.json"
SAVE_MONSTER_RAID = "raid_status.json"


class LobFullEgoPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        plugin_dir = Path(__file__).parent
        self.data_dir = plugin_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        self.weapon_lib = self._load(SAVE_WEAPON)
        self.armor_lib = self._load(SAVE_ARMOR)
        self.trinket_lib = self._load(SAVE_TRINKET)
        self.monster_lib = self._load(SAVE_MONSTER)
        self.staff_data = self._load(SAVE_STAFF)
        self.cd_data = self._load(SAVE_COOLDOWN)
        self.attack_stack = self._load(SAVE_ATTACK_STACK)
        self.dodge_queue = self._load(SAVE_DODGE_QUEUE)
        self.dying_queue = self._load(SAVE_DYING_QUEUE)
        self.raid_status = self._load(SAVE_MONSTER_RAID)
        
        logger.info(f"脑叶公司插件已加载，数据目录: {self.data_dir}")
        logger.info(f"已加载员工: {list(self.staff_data.keys())}")

    def _path(self, filename):
        return str(self.data_dir / filename)

    def _load(self, filename):
        try:
            with open(self._path(filename), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, filename, data):
        with open(self._path(filename), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_all(self):
        self._save(SAVE_WEAPON, self.weapon_lib)
        self._save(SAVE_ARMOR, self.armor_lib)
        self._save(SAVE_TRINKET, self.trinket_lib)
        self._save(SAVE_MONSTER, self.monster_lib)
        self._save(SAVE_STAFF, self.staff_data)
        self._save(SAVE_COOLDOWN, self.cd_data)
        self._save(SAVE_ATTACK_STACK, self.attack_stack)
        self._save(SAVE_DODGE_QUEUE, self.dodge_queue)
        self._save(SAVE_DYING_QUEUE, self.dying_queue)
        self._save(SAVE_MONSTER_RAID, self.raid_status)

    def _get_staff_max_hp(self, staff):
        if staff["armor"] == "无":
            return ARMOR_HP_BASE["HE"]
        elif staff["armor"] in self.armor_lib:
            armor_lv = self.armor_lib[staff["armor"]]["level"]
            base_hp = ARMOR_HP_BASE.get(armor_lv, 6.0)
        else:
            base_hp = 6.0
        hp_add = 0
        for t_name in staff.get("trinkets", []):
            if t_name in self.trinket_lib and self.trinket_lib[t_name]["prop"] == "hp":
                hp_add += self.trinket_lib[t_name]["val"] * 0.1
        return base_hp + hp_add

    def _calculate_single_damage(self, weapon, target_resistances, level_diff, atk_mod, bonus):
        """计算单次伤害，最低0.1"""
        dmg_type = weapon["dmg_type"]
        dmg_map = {"物理": "phy", "精神": "spi", "侵蚀": "cor", "灵魂": "sou"}
        base_res = target_resistances.get(dmg_map.get(dmg_type, "phy"), 1.0)
        raw_damage = base_res + level_diff * 0.2 + atk_mod + bonus
        return max(0.1, raw_damage)

    # ==================== 测试指令 ====================
    @filter.command(".test")
    async def cmd_test(self, event: AstrMessageEvent):
        yield event.plain_result("✅ 脑叶公司插件正常工作！")

    # ==================== 武器管理 ====================
    @filter.command(".addweapon")
    async def cmd_add_weapon(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 5:
            yield event.plain_result("格式：.addweapon 武器名 伤害类型 射速 评级\n例：.addweapon 随便 精神 快 HE\n射速：极快/快/一般/慢/极慢\n评级：HE/WAW/ALEPH")
            return
        _, name, dmg_type, speed, lv = args
        lv = lv.strip().upper()
        if name in self.weapon_lib:
            yield event.plain_result(f"武器【{name}】已存在")
            return
        if speed not in SPEED_CD_MAP:
            yield event.plain_result(f"射速可选：{list(SPEED_CD_MAP.keys())}")
            return
        if lv not in LEVEL_WEIGHT:
            yield event.plain_result(f"评级可选：{list(LEVEL_WEIGHT.keys())}")
            return
        self.weapon_lib[name] = {"dmg_type": dmg_type, "speed": speed, "level": lv}
        self._save_all()
        yield event.plain_result(f"✅ 录入武器【{name}】成功")

    @filter.command(".listweapon")
    async def cmd_list_weapon(self, event: AstrMessageEvent):
        if not self.weapon_lib:
            yield event.plain_result("暂无武器数据")
            return
        msg = "=== EGO武器库 ===\n"
        for n, v in self.weapon_lib.items():
            msg += f"{n} | {v['dmg_type']} | {v['speed']} | 评级:{v['level']}\n"
        yield event.plain_result(msg)

    @filter.command(".delweapon")
    async def cmd_del_weapon(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.delweapon 武器名")
            return
        _, n = args
        if n in self.weapon_lib:
            del self.weapon_lib[n]
            self._save_all()
            yield event.plain_result(f"已删除武器【{n}】")
            return
        yield event.plain_result("无此武器")

    # ==================== 护甲管理 ====================
    @filter.command(".addarmor")
    async def cmd_add_armor(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 7:
            yield event.plain_result("格式：.addarmor 护甲名 物理 精神 侵蚀 灵魂 评级\n例：.addarmor 都行 1.0 0.5 0.7 1.7 HE")
            return
        _, name, phy, spi, cor, sou, lv = args
        lv = lv.strip().upper()
        if name in self.armor_lib:
            yield event.plain_result(f"护甲【{name}】已存在")
            return
        try:
            phy, spi, cor, sou = float(phy), float(spi), float(cor), float(sou)
        except:
            yield event.plain_result("抗性必须是数字")
            return
        if lv not in LEVEL_WEIGHT:
            yield event.plain_result(f"评级可选：{list(LEVEL_WEIGHT.keys())}")
            return
        self.armor_lib[name] = {"phy": phy, "spi": spi, "cor": cor, "sou": sou, "level": lv}
        self._save_all()
        yield event.plain_result(f"✅ 录入护甲【{name}】成功")

    @filter.command(".listarmor")
    async def cmd_list_armor(self, event: AstrMessageEvent):
        if not self.armor_lib:
            yield event.plain_result("暂无护甲")
            return
        msg = "=== EGO护甲库 ===\n"
        for n, v in self.armor_lib.items():
            msg += f"{n} | 物理:{v['phy']} 精神:{v['spi']} 侵蚀:{v['cor']} 灵魂:{v['sou']} | 评级:{v['level']}\n"
        yield event.plain_result(msg)

    @filter.command(".delarmor")
    async def cmd_del_armor(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.delarmor 护甲名")
            return
        _, n = args
        if n in self.armor_lib:
            del self.armor_lib[n]
            self._save_all()
            yield event.plain_result(f"已删除护甲【{n}】")
            return
        yield event.plain_result("无此护甲")

    # ==================== 饰品管理 ====================
    @filter.command(".addtrinket")
    async def cmd_add_trinket(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 4:
            yield event.plain_result("格式：.addtrinket 饰品名 属性 数值\n属性：hp/sp/atk/spd/succ")
            return
        _, name, prop, val = args
        if name in self.trinket_lib:
            yield event.plain_result(f"饰品【{name}】已存在")
            return
        if prop not in VALID_TRINKET_PROP:
            yield event.plain_result(f"合法属性：{VALID_TRINKET_PROP}")
            return
        try:
            val = float(val)
        except:
            yield event.plain_result("数值必须是数字")
            return
        self.trinket_lib[name] = {"prop": prop, "val": val}
        self._save_all()
        yield event.plain_result(f"✅ 录入饰品【{name}】成功")

    @filter.command(".listtrinket")
    async def cmd_list_trinket(self, event: AstrMessageEvent):
        if not self.trinket_lib:
            yield event.plain_result("暂无饰品")
            return
        msg = "=== EGO饰品库 ===\n"
        for n, v in self.trinket_lib.items():
            msg += f"{n} | {v['prop']} {v['val']}\n"
        yield event.plain_result(msg)

    @filter.command(".deltrinket")
    async def cmd_del_trinket(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.deltrinket 饰品名")
            return
        _, n = args
        if n in self.trinket_lib:
            del self.trinket_lib[n]
            self._save_all()
            yield event.plain_result(f"已删除饰品【{n}】")
            return
        yield event.plain_result("无此饰品")

    # ==================== 异想体管理 ====================
        @filter.command(".addmonster")
        async def cmd_add_monster(self, event: AstrMessageEvent):
         """录入异想体：.addmonster 名称 编号 伤害类型 评级 物理 精神 侵蚀 灵魂 移速 计数器极值"""
        args = event.message_str.strip().split()
        if len(args) < 10:
            yield event.plain_result("格式：.addmonster 名称 编号 伤害类型 评级 物理 精神 侵蚀 灵魂 移速 计数器极值\n例：.addmonster 西里安 O-01-45 侵蚀 HE 1.0 0.7 0.7 1.7 10 3")
            return
        
        _, name, code, dmg_t, lv, phy, spi, cor, sou, spd, q_max = args[:11]
        
        lv = lv.strip().upper()
        if name in self.monster_lib:
            yield event.plain_result(f"异想体【{name}】已存在")
            return
        try:
            phy, spi, cor, sou, spd = float(phy), float(spi), float(cor), float(sou), float(spd)
            q_max = int(q_max)
        except:
            yield event.plain_result("抗性、移速必须是数字，计数器必须是整数")
            return
        if lv not in LEVEL_WEIGHT:
            yield event.plain_result(f"评级可选：{list(LEVEL_WEIGHT.keys())}")
            return
        
        self.monster_lib[name] = {
            "code": code,
            "atk_type": dmg_t, "level": lv,
            "phy": phy, "spi": spi, "cor": cor, "sou": sou, "speed": spd,
            "q_counter_max": q_max,      # 计数器最大值
            "q_counter": q_max           # 当前计数器值
        }
        
        self._save_all()
        yield event.plain_result(f"✅ 录入异想体【{name}】（{code}）成功\n逆卡巴拉计数器：{q_max}/{q_max}")

    @filter.command(".listmonster")
    async def cmd_list_monster(self, event: AstrMessageEvent):
        if not self.monster_lib:
            yield event.plain_result("暂无异想体")
            return
        msg = "=== 异想体库 ===\n"
        for n, v in self.monster_lib.items():
            msg += f"{n} | 伤害:{v['atk_type']} 评级:{v['level']} 移速:{v['speed']}\n"
        yield event.plain_result(msg)

    @filter.command(".delmonster")
    async def cmd_del_monster(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.delmonster 异想体名")
            return
        _, n = args
        if n in self.monster_lib:
            del self.monster_lib[n]
            self._save_all()
            yield event.plain_result(f"已删除异想体【{n}】")
            return
        yield event.plain_result("无此异想体")

    @filter.command(".出逃")
    async def cmd_escape(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.出逃 异想体名")
            return
        m_name = args[1]
        if m_name not in self.monster_lib:
            yield event.plain_result(f"异想体【{m_name}】不存在")
            return
        m_info = self.monster_lib[m_name]
        self.raid_status[m_name] = {"is_raid": True, "hp": MONSTER_HP_BASE[m_info["level"]]}
        self._save_all()
        yield event.plain_result(f"⚠️【{m_name}】突破收容出逃！生命值：{MONSTER_HP_BASE[m_info['level']]}")

    # ==================== 员工管理 ====================
    @filter.command(".regstaff")
    async def cmd_reg_staff(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 5:
            yield event.plain_result("格式：.regstaff 员工名 武器名 护甲名 饰品1,饰品2\n例：.regstaff 玛蒂尔达 随便 都行 我,终于,成功了")
            return
        staff_name, weapon, armor, trinket_str = args[1], args[2], args[3], args[4]
        
        if weapon != "无" and weapon not in self.weapon_lib:
            yield event.plain_result(f"武器【{weapon}】不存在，请先使用 .addweapon 录入")
            return
        if armor != "无" and armor not in self.armor_lib:
            yield event.plain_result(f"护甲【{armor}】不存在，请先使用 .addarmor 录入")
            return
        
        trinket_list = []
        if trinket_str != "无":
            trinket_list = [t.strip() for t in trinket_str.split(",")]
            for t in trinket_list:
                if t not in self.trinket_lib:
                    yield event.plain_result(f"饰品【{t}】不存在，请先使用 .addtrinket 录入")
                    return
        
        armor_lv = self.armor_lib[armor]["level"] if armor != "无" else "HE"
        base_hp = ARMOR_HP_BASE[armor_lv]
        
        self.staff_data[staff_name] = {
            "weapon": weapon, "armor": armor, "trinkets": trinket_list,
            "max_trinket_slot": DEFAULT_TRINKET_SLOT, "hp": base_hp,
            "is_dying": False, "is_crazy": False, "crazy_value": 0,
            "is_dead": False  # 新增死亡标记
        }
        self._save_all()
        yield event.plain_result(f"✅ 员工【{staff_name}】注册成功\n初始生命值：{base_hp}")

    @filter.command(".staffinfo")
    async def cmd_staff_info(self, event: AstrMessageEvent):
        """查看员工状态（包含存储攻击和冷却）"""
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.staffinfo 员工名")
            return
        
        s_name = args[1]
        if s_name not in self.staff_data:
            yield event.plain_result(f"员工【{s_name}】不存在\n已注册员工：{list(self.staff_data.keys())}")
            return
        
        s = self.staff_data[s_name]
        arm = self.armor_lib[s["armor"]] if s["armor"] != "无" else {"phy": 1.0, "spi": 1.0, "cor": 1.0, "sou": 1.0, "level": "HE"}
        max_hp = self._get_staff_max_hp(s)
        
        # 计算移速
        spd_add = 0
        for t_name in s["trinkets"]:
            if t_name in self.trinket_lib and self.trinket_lib[t_name]["prop"] == "spd":
                spd_add += self.trinket_lib[t_name]["val"]
        staff_spd = 4 + (100 + spd_add) * 0.04
        
        weapon_info = self.weapon_lib[s["weapon"]] if s["weapon"] != "无" else {"dmg_type": "无", "speed": "无"}
        
        # 获取武器CD时间
        weapon_speed = weapon_info.get("speed", "一般")
        cd_seconds = SPEED_CD_MAP.get(weapon_speed, 60 * 60)
        
        # 收集所有存储攻击和冷却信息
        now = time.time()
        stored_info = []
        
        for cd_key, last_time in self.cd_data.items():
            if cd_key.startswith(f"{s_name}_"):
                target = cd_key.replace(f"{s_name}_", "")
                time_since_last = now - last_time
                if time_since_last < cd_seconds:
                    remaining = cd_seconds - time_since_last
                    stored_info.append(f"  • 对【{target}】冷却剩余：{round(remaining/60, 1)} 分钟")
        
        for stack_key, count in self.attack_stack.items():
            if stack_key.startswith(f"{s_name}_"):
                target = stack_key.replace(f"{s_name}_", "")
                stored_info.append(f"  • 对【{target}】存储攻击：{count} 次")
        
        # 去重并格式化
        unique_stored = {}
        for info in stored_info:
            key = info.split("：")[0]
            if key not in unique_stored:
                unique_stored[key] = info
        stored_list = list(unique_stored.values())
        
        msg = (
            f"=====员工【{s_name}】状态=====\n"
            f"剩余生命值：{round(s['hp'], 2)} / {round(max_hp, 2)}\n"
            f"疯狂状态：{'是' if s.get('is_crazy') else '否'}"
        )
        if s.get('is_crazy'):
            msg += f"\n疯狂值：{round(s.get('crazy_value', 0), 2)} / {round(max_hp, 2)}"
        msg += (
            f"\n装备武器：{s['weapon']} | 伤害:{weapon_info['dmg_type']} | 射速:{weapon_speed}（CD:{round(cd_seconds/60, 0)}分钟）\n"
            f"装备护甲：{s['armor']}\n"
            f"四抗性：物理:{arm['phy']} 精神:{arm['spi']} 侵蚀:{arm['cor']} 灵魂:{arm['sou']}\n"
            f"移速数值：{round(staff_spd, 2)}\n"
            f"携带饰品：{s['trinkets']}（槽位上限{s['max_trinket_slot']}）\n"
            f"濒死状态：{s['is_dying']}"
        )
        
        if stored_list:
            msg += "\n\n=== 待生效状态 ===\n" + "\n".join(stored_list)
        else:
            msg += "\n\n=== 待生效状态 ===\n  无存储攻击，无冷却"
        
        yield event.plain_result(msg)

    @filter.command(".饰品槽")
    async def cmd_add_slot(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 3:
            yield event.plain_result("格式：.饰品槽 员工名 +2")
            return
        s_name, delta = args[1], args[2]
        if s_name not in self.staff_data:
            yield event.plain_result("无此员工")
            return
        try:
            delta = int(delta)
        except:
            yield event.plain_result("增量必须是整数")
            return
        self.staff_data[s_name]["max_trinket_slot"] += delta
        self._save_all()
        yield event.plain_result(f"【{s_name}】饰品槽变更为：{self.staff_data[s_name]['max_trinket_slot']}")

    # ==================== 疯狂系统 ====================
    @filter.command(".陷入疯狂")
    async def cmd_go_crazy(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.陷入疯狂 员工名")
            return
        s_name = args[1]
        if s_name not in self.staff_data:
            yield event.plain_result(f"员工【{s_name}】不存在")
            return
        staff = self.staff_data[s_name]
        if staff["is_dying"]:
            yield event.plain_result(f"【{s_name}】濒死，无法疯狂")
            return
        if staff.get("is_dead", False):
            yield event.plain_result(f"【{staff_name}】已经死亡，无法进行任何操作")
            return
        if staff.get("is_crazy"):
            yield event.plain_result(f"【{s_name}】已处于疯狂状态")
            return
        max_hp = self._get_staff_max_hp(staff)
        staff["is_crazy"] = True
        staff["crazy_value"] = max_hp
        self._save_all()
        yield event.plain_result(f"⚠️【{s_name}】陷入疯狂！\n疯狂值：{max_hp}/{max_hp}")

    @filter.command(".解除疯狂")
    async def cmd_calm_down(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.解除疯狂 员工名")
            return
        s_name = args[1]
        if s_name not in self.staff_data:
            yield event.plain_result(f"员工【{s_name}】不存在")
            return
        staff = self.staff_data[s_name]
        if not staff.get("is_crazy"):
            yield event.plain_result(f"【{s_name}】不处于疯狂状态")
            return
        staff["is_crazy"] = False
        staff["crazy_value"] = 0
        self._save_all()
        yield event.plain_result(f"✅【{s_name}】已解除疯狂状态")

    # ==================== 休息 ====================
    @filter.command(".休息")
    async def cmd_rest(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.休息 员工名")
            return
        s_name = args[1]
        if s_name not in self.staff_data:
            yield event.plain_result("无此员工")
            return
        staff = self.staff_data[s_name]
        if staff.get("is_dead", False):
            yield event.plain_result(f"【{staff_name}】已经死亡，无法进行任何操作")
            return
        if staff["is_dying"]:
            yield event.plain_result("濒死无法休息")
            return
        max_hp = self._get_staff_max_hp(staff)
        old_hp = staff["hp"]
        staff["hp"] = min(staff["hp"] + REST_HP_RECOVER, max_hp)
        self._save_all()
        yield event.plain_result(f"{s_name} 前往大厅休息，恢复 {REST_HP_RECOVER} 生命值\n{round(old_hp, 2)} → {round(staff['hp'], 2)} / {round(max_hp, 2)}")

       # ==================== 核心：员工攻击异想体（只能攻击异想体） ====================
    @filter.command(".进行攻击")
    async def cmd_staff_attack(self, event: AstrMessageEvent):
        """员工攻击异想体：员工名 对 异想体名 进行 Y次攻击，此攻击加成为 X"""
        raw = event.message_str.strip()
        # 移除指令前缀
        if raw.startswith(".进行攻击 "):
            content = raw[5:].strip()
        else:
            content = raw
        
        import re
        # 支持 "员工名 对 异想体名" 或 "员工名对异想体名"
        pattern = r'(.+?)\s*对\s*(.+?)\s*进行\s*(\d+)\s*次攻击\s*，\s*此攻击加成为\s*([\-0-9.]+)'
        match = re.search(pattern, content)
        
        if not match:
            yield event.plain_result("格式错误！\n正确格式：.进行攻击 员工名 对 异想体名 进行 Y次攻击，此攻击加成为 X\n例：.进行攻击 玛蒂尔达 对 西里安 进行 3次攻击，此攻击加成为 0.2")
            return
        
        staff_name = match.group(1).strip()
        target_name = match.group(2).strip()
        try:
            attack_count = int(match.group(3))
            bonus = float(match.group(4))
        except:
            yield event.plain_result("攻击次数必须是数字，加成必须是数字")
            return
        
        if attack_count <= 0:
            yield event.plain_result("攻击次数必须大于0")
            return
        
        # 验证员工
        if staff_name not in self.staff_data:
            yield event.plain_result(f"员工【{staff_name}】不存在\n已注册员工：{list(self.staff_data.keys())}")
            return
        
        # 验证目标必须是异想体
        if target_name not in self.monster_lib:
            yield event.plain_result(f"目标【{target_name}】不是异想体！\n攻击异想体请使用 .进行攻击\n攻击疯狂员工请使用 .攻击疯狂")
            return
        
        # 验证是否出逃
        raid_info = self.raid_status.get(target_name, {})
        if not raid_info.get("is_raid", False):
            yield event.plain_result(f"【{target_name}】并未出逃，无法攻击\n请先使用 .出逃 {target_name}")
            return
        
        staff = self.staff_data[staff_name]
        if staff["is_dying"]:
            yield event.plain_result(f"【{staff_name}】处于濒死状态，无法攻击")
            return
        
        if staff.get("is_dead", False):
            yield event.plain_result(f"【{staff_name}】已经死亡，无法进行任何操作")
            return
        
        if staff["weapon"] == "无":
            yield event.plain_result(f"【{staff_name}】未装备武器")
            return
        
        if staff["weapon"] not in self.weapon_lib:
            yield event.plain_result(f"武器【{staff['weapon']}】数据不存在")
            return
        
        weapon = self.weapon_lib[staff["weapon"]]
        monster = self.monster_lib[target_name]
        
        # 计算单次伤害
        resistances = {"phy": monster["phy"], "spi": monster["spi"], "cor": monster["cor"], "sou": monster["sou"]}
        w_lv = LEVEL_WEIGHT.get(weapon["level"], 1)
        m_lv = LEVEL_WEIGHT.get(monster["level"], 1)
        level_diff = w_lv - m_lv
        
        atk_mod = 0
        for t in staff["trinkets"]:
            if t in self.trinket_lib and self.trinket_lib[t]["prop"] == "atk":
                atk_mod += self.trinket_lib[t]["val"] * 0.1
        
        single_damage = self._calculate_single_damage(weapon, resistances, level_diff, atk_mod, bonus)
        
        # CD检查
        cd_key = f"{staff_name}_{target_name}"
        cd_seconds = SPEED_CD_MAP.get(weapon["speed"], 60 * 60)
        last_attack_time = self.cd_data.get(cd_key, 0)
        now = time.time()
        time_since_last = now - last_attack_time
        
        msg = ""
        
        if time_since_last >= cd_seconds:
            # 无冷却，可以立即攻击
            stack_key = cd_key
            total_stored = self.attack_stack.get(stack_key, 0)
            
            if total_stored > 0:
                self.attack_stack[stack_key] = 0
                total_damage = single_damage * total_stored
                self.raid_status[target_name]["hp"] -= total_damage
                msg += f"【{staff_name}】的武器冷却已结束，释放存储的 {total_stored} 次攻击，造成 {round(total_damage, 2)} 点伤害！\n"
            
            total_damage_now = single_damage * attack_count
            self.raid_status[target_name]["hp"] -= total_damage_now
            self.cd_data[cd_key] = now
            msg += f"{staff_name} 使用 {staff['weapon']} 攻击 {target_name}，造成 {round(total_damage_now, 2)} 点伤害！"
            
        else:
            remaining_cd = cd_seconds - time_since_last
            stack_key = cd_key
            if stack_key not in self.attack_stack:
                self.attack_stack[stack_key] = 0
            self.attack_stack[stack_key] += attack_count
            msg = f"{staff_name} 的武器处于冷却中（剩余 {round(remaining_cd/60, 1)} 分钟），{attack_count} 次攻击已存入堆栈，冷却结束后将自动释放。"
        
        # 检查异想体是否死亡
        if self.raid_status[target_name]["hp"] <= 0:
            self.raid_status[target_name]["is_raid"] = False
            msg += f"\n✅【{target_name}】血量归零，已被镇压！"
        
        self._save_all()
        yield event.plain_result(msg)

    # ==================== 核心：攻击疯狂员工 ====================
    @filter.command(".攻击疯狂")
    async def cmd_attack_crazy(self, event: AstrMessageEvent):
        """攻击疯狂员工：攻击者名 对 目标名 进行 Y次攻击，此攻击加成为 X
        规则：只要攻击者或目标中有一方是疯狂员工，就可以攻击
        """
        raw = event.message_str.strip()
        if raw.startswith(".攻击疯狂 "):
            content = raw[5:].strip()
        else:
            content = raw
        
        import re
        pattern = r'(.+?)\s*对\s*(.+?)\s*进行\s*(\d+)\s*次攻击\s*，\s*此攻击加成为\s*([\-0-9.]+)'
        match = re.search(pattern, content)
        
        if not match:
            yield event.plain_result("格式错误！\n正确格式：.攻击疯狂 攻击者名 对 目标名 进行 Y次攻击，此攻击加成为 X\n例：.攻击疯狂 玛蒂尔达 对 张三 进行 3次攻击，此攻击加成为 0.2\n规则：只要一方是疯狂状态即可攻击")
            return
        
        attacker_name = match.group(1).strip()
        target_name = match.group(2).strip()
        try:
            attack_count = int(match.group(3))
            bonus = float(match.group(4))
        except:
            yield event.plain_result("攻击次数必须是数字，加成必须是数字")
            return
        
        if attack_count <= 0:
            yield event.plain_result("攻击次数必须大于0")
            return
        
        # 验证攻击者
        if attacker_name not in self.staff_data:
            yield event.plain_result(f"攻击者【{attacker_name}】不存在\n已注册员工：{list(self.staff_data.keys())}")
            return
        
        # 验证目标必须是员工
        if target_name not in self.staff_data:
            yield event.plain_result(f"目标【{target_name}】不是员工\n已注册员工：{list(self.staff_data.keys())}")
            return
        
        attacker = self.staff_data[attacker_name]
        target = self.staff_data[target_name]
        
        # 新规则：只要有一方是疯狂员工，就可以攻击
        if not attacker.get("is_crazy", False) and not target.get("is_crazy", False):
            yield event.plain_result("无法攻击！攻击双方都处于正常状态。\n只有疯狂员工才能参与战斗。\n请先使用 .陷入疯狂 让其中一方陷入疯狂")
            return
        
        if attacker["is_dying"]:
            yield event.plain_result(f"【{attacker_name}】处于濒死状态，无法攻击")
            return
        
        if staff.get("is_dead", False):
            yield event.plain_result(f"【{staff_name}】已经死亡，无法进行任何操作")
            return
        
        if target["is_dying"]:
            yield event.plain_result(f"【{target_name}】已濒死，无法继续受伤")
            return
        
        if attacker["weapon"] == "无":
            yield event.plain_result(f"【{attacker_name}】未装备武器")
            return
        
        if attacker["weapon"] not in self.weapon_lib:
            yield event.plain_result(f"武器【{attacker['weapon']}】数据不存在")
            return
        
        weapon = self.weapon_lib[attacker["weapon"]]
        
        # 获取目标护甲抗性
        if target["armor"] != "无" and target["armor"] in self.armor_lib:
            arm = self.armor_lib[target["armor"]]
            resistances = {"phy": arm["phy"], "spi": arm["spi"], "cor": arm["cor"], "sou": arm["sou"]}
        else:
            resistances = {"phy": 1.0, "spi": 1.0, "cor": 1.0, "sou": 1.0}
        
        # 计算攻击加成
        atk_mod = 0
        for t in attacker["trinkets"]:
            if t in self.trinket_lib and self.trinket_lib[t]["prop"] == "atk":
                atk_mod += self.trinket_lib[t]["val"] * 0.1
        
        dmg_type = weapon["dmg_type"]
        dmg_map = {"物理": "phy", "精神": "spi", "侵蚀": "cor", "灵魂": "sou"}
        base_res = resistances.get(dmg_map.get(dmg_type, "phy"), 1.0)
        
        # 员工之间没有等级修正
        single_damage = max(0.1, base_res + atk_mod + bonus)
        total_damage = single_damage * attack_count
        
        is_target_crazy = target.get("is_crazy", False)
        msg = ""
        
        if is_target_crazy:
            # 目标疯狂
            if dmg_type == "精神":
                target["crazy_value"] = max(0, target["crazy_value"] - total_damage)
                msg = f"{attacker_name} 使用精神武器攻击疯狂状态的 {target_name}，扣除 {round(total_damage, 2)} 疯狂值"
                if target["crazy_value"] <= 0:
                    target["is_crazy"] = False
                    target["crazy_value"] = 0
                    msg += f"\n✅【{target_name}】的疯狂值归零，已解除疯狂状态"
            elif dmg_type == "侵蚀":
                half = total_damage / 2
                target["crazy_value"] = max(0, target["crazy_value"] - half)
                target["hp"] = max(0, target["hp"] - half)
                msg = f"{attacker_name} 使用侵蚀武器攻击疯狂状态的 {target_name}，扣除 {round(half, 2)} 生命和 {round(half, 2)} 疯狂值"
                if target["crazy_value"] <= 0:
                    target["is_crazy"] = False
                    target["crazy_value"] = 0
                    msg += f"\n✅【{target_name}】的疯狂值归零，已解除疯狂状态"
                if target["hp"] <= 0:
                    target["is_dying"] = True
                    target["is_crazy"] = False
                    now = time.time()
                    self.dying_queue[target_name] = {"expire": now + DYING_RESCUE_EXPIRE}
                    msg += f"\n💀【{target_name}】生命值归零，陷入濒死状态"
            else:
                target["hp"] = max(0, target["hp"] - total_damage)
                msg = f"{attacker_name} 攻击疯狂状态的 {target_name}，造成 {round(total_damage, 2)} 生命伤害"
                if target["hp"] <= 0:
                    target["is_dying"] = True
                    target["is_crazy"] = False
                    now = time.time()
                    self.dying_queue[target_name] = {"expire": now + DYING_RESCUE_EXPIRE}
                    msg += f"\n💀【{target_name}】生命值归零，陷入濒死状态"
        else:
            # 目标正常，攻击者疯狂
            target["hp"] = max(0, target["hp"] - total_damage)
            msg = f"{attacker_name}（疯狂）攻击正常员工 {target_name}，造成 {round(total_damage, 2)} 生命伤害"
            if target["hp"] <= 0:
                target["is_dying"] = True
                now = time.time()
                self.dying_queue[target_name] = {"expire": now + DYING_RESCUE_EXPIRE}
                msg += f"\n💀【{target_name}】生命值归零，陷入濒死状态"
        
        self._save_all()
        yield event.plain_result(msg)

    # ==================== 核心：异想体攻击指令 ====================
    @filter.command(".异想攻击")
    async def cmd_monster_attack(self, event: AstrMessageEvent):
        """异想体攻击员工：异想体名 对 员工名 进行 Y次攻击，此攻击加成为 X"""
        raw = event.message_str.strip()
        if raw.startswith(".异想攻击 "):
            content = raw[5:].strip()
        else:
            content = raw
        
        import re
        # 支持 "异想体名 对 员工名" 或 "异想体名对员工名"
        pattern = r'(.+?)\s*对\s*(.+?)\s*进行\s*(\d+)\s*次攻击\s*，\s*此攻击加成为\s*([\-0-9.]+)'
        match = re.search(pattern, content)
        
        if not match:
            yield event.plain_result("格式错误！\n正确格式：.异想攻击 异想体名 对 员工名 进行 Y次攻击，此攻击加成为 X\n例：.异想攻击 西里安 对 玛蒂尔达 进行 2次攻击，此攻击加成为 0.1")
            return
        
        monster_name = match.group(1).strip()
        staff_name = match.group(2).strip()
        try:
            attack_count = int(match.group(3))
            bonus = float(match.group(4))
        except:
            yield event.plain_result("攻击次数必须是数字，加成必须是数字")
            return
        
        if attack_count <= 0:
            yield event.plain_result("攻击次数必须大于0")
            return
        
        # 验证异想体
        if monster_name not in self.monster_lib:
            yield event.plain_result(f"异想体【{monster_name}】不存在\n已录入异想体：{list(self.monster_lib.keys())}")
            return
        
        # 验证员工
        if staff_name not in self.staff_data:
            yield event.plain_result(f"员工【{staff_name}】不存在\n已注册员工：{list(self.staff_data.keys())}")
            return
        
        # 验证异想体是否出逃
        raid_info = self.raid_status.get(monster_name, {})
        if not raid_info.get("is_raid", False):
            yield event.plain_result(f"【{monster_name}】并未出逃，无法攻击")
            return
        
        staff = self.staff_data[staff_name]
        if staff["is_dying"]:
            yield event.plain_result(f"【{staff_name}】已濒死，无法继续受伤")
            return
        
        monster = self.monster_lib[monster_name]
        
        # 获取员工护甲抗性
        if staff["armor"] != "无" and staff["armor"] in self.armor_lib:
            arm = self.armor_lib[staff["armor"]]
            resistances = {"phy": arm["phy"], "spi": arm["spi"], "cor": arm["cor"], "sou": arm["sou"]}
        else:
            resistances = {"phy": 1.0, "spi": 1.0, "cor": 1.0, "sou": 1.0}
        
        # 计算单次伤害
        dmg_type = monster["atk_type"]
        dmg_map = {"物理": "phy", "精神": "spi", "侵蚀": "cor", "灵魂": "sou"}
        base_res = resistances.get(dmg_map.get(dmg_type, "phy"), 1.0)
        single_damage = max(0.1, base_res + bonus)
        total_damage = single_damage * attack_count
        
        # 计算员工移速
        spd_add = 0
        for t in staff["trinkets"]:
            if t in self.trinket_lib and self.trinket_lib[t]["prop"] == "spd":
                spd_add += self.trinket_lib[t]["val"]
        staff_spd = 4 + (100 + spd_add) * 0.04
        monster_spd = monster["speed"]
        
        now = time.time()
        
        if staff_spd > monster_spd:
            dodge_key = staff_name
            self.dodge_queue[dodge_key] = {
                "expire": now + DODGE_EXPIRE,
                "pending_dmg": total_damage,
                "source_monster": monster_name,
                "attack_count": attack_count
            }
            self._save_all()
            yield event.plain_result(f"@{staff_name} 你的移速高于 {monster_name}，可以在1小时内回复 .闪避 来规避本次 {round(total_damage, 2)} 点总伤害（{attack_count}次攻击）")
            return
        
        # 直接承受伤害
        staff["hp"] -= total_damage
        msg = f"{monster_name} 攻击 {staff_name}，造成 {round(total_damage, 2)} 点伤害！"
        
        if staff["hp"] <= 0:
            staff["is_dying"] = True
            staff["is_crazy"] = False
            self.dying_queue[staff_name] = {"expire": now + DYING_RESCUE_EXPIRE}
            msg += f"\n💀【{staff_name}】生命值归零，陷入濒死状态！1小时内可救援"
        
        self._save_all()
        yield event.plain_result(msg)
            
       # ==================== 异想体互殴 ====================
    @filter.command(".异想体互殴")
    async def cmd_monster_fight(self, event: AstrMessageEvent):
        """异想体互殴：异想体A 对 异想体B 进行 Y次攻击，此攻击加成为 X"""
        raw = event.message_str.strip()
        
        # 移除艾特前缀
        if raw.startswith("@") and " " in raw:
            raw = raw.split(" ", 1)[1]
        
        # 移除指令前缀
        if raw.startswith(".异想体互殴 "):
            content = raw[6:].strip()
        elif raw.startswith("异想体互殴 "):
            content = raw[5:].strip()
        else:
            content = raw
        
        import re
        pattern = r'(.+?)\s*对\s*(.+?)\s*进行\s*(\d+)\s*次攻击\s*，\s*此攻击加成为\s*([\-0-9.]+)'
        match = re.search(pattern, content)
        
        if not match:
            yield event.plain_result("格式错误！\n正确格式：.异想体互殴 异想体A 对 异想体B 进行 Y次攻击，此攻击加成为 X\n例：.异想体互殴 西里安 对 死别 进行 3次攻击，此攻击加成为 0.2")
            return
        
        attacker_name = match.group(1).strip()
        target_name = match.group(2).strip()
        try:
            attack_count = int(match.group(3))
            bonus = float(match.group(4))
        except:
            yield event.plain_result("攻击次数必须是数字，加成必须是数字")
            return
        
        if attack_count <= 0:
            yield event.plain_result("攻击次数必须大于0")
            return
        
        # 验证攻击者异想体
        if attacker_name not in self.monster_lib:
            yield event.plain_result(f"异想体【{attacker_name}】不存在\n已录入异想体：{list(self.monster_lib.keys())}")
            return
        
        # 验证目标异想体
        if target_name not in self.monster_lib:
            yield event.plain_result(f"异想体【{target_name}】不存在\n已录入异想体：{list(self.monster_lib.keys())}")
            return
        
        # 验证双方是否都出逃
        raid_attacker = self.raid_status.get(attacker_name, {})
        raid_target = self.raid_status.get(target_name, {})
        
        if not raid_attacker.get("is_raid", False):
            yield event.plain_result(f"【{attacker_name}】并未出逃，无法攻击")
            return
        
        if not raid_target.get("is_raid", False):
            yield event.plain_result(f"【{target_name}】并未出逃，无法攻击")
            return
        
        attacker = self.monster_lib[attacker_name]
        target = self.monster_lib[target_name]
        
        # 获取目标抗性
        dmg_type = attacker["atk_type"]
        dmg_map = {"物理": "phy", "精神": "spi", "侵蚀": "cor", "灵魂": "sou"}
        base_res = target.get(dmg_map.get(dmg_type, "phy"), 1.0)
        
        # 等级差修正
        a_lv = LEVEL_WEIGHT.get(attacker["level"], 1)
        t_lv = LEVEL_WEIGHT.get(target["level"], 1)
        level_diff = a_lv - t_lv
        
        single_damage = max(0.1, base_res + level_diff * 0.2 + bonus)
        total_damage = single_damage * attack_count
        
        # 造成伤害
        self.raid_status[target_name]["hp"] -= total_damage
        msg = f"{attacker_name} 攻击 {target_name}，造成 {round(total_damage, 2)} 点伤害！"
        
        # 检查目标是否死亡
        if self.raid_status[target_name]["hp"] <= 0:
            self.raid_status[target_name]["is_raid"] = False
            msg += f"\n✅【{target_name}】血量归零，已被镇压！"
        
        self._save_all()
        yield event.plain_result(msg)
    # ==================== 闪避 ====================
    @filter.command(".闪避")
    async def cmd_dodge(self, event: AstrMessageEvent):
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.闪避 员工名")
            return
        s_name = args[1]
        
        if s_name not in self.dodge_queue:
            yield event.plain_result(f"【{s_name}】没有待闪避的攻击")
            return
        
        dodge_data = self.dodge_queue[s_name]
        now = time.time()
        
        if now > dodge_data["expire"]:
            del self.dodge_queue[s_name]
            self._save_all()
            # 时效已过，伤害自动生效
            staff = self.staff_data.get(s_name)
            if staff:
                staff["hp"] -= dodge_data["pending_dmg"]
                if staff["hp"] <= 0:
                    staff["is_dying"] = True
                    self.dying_queue[s_name] = {"expire": now + DYING_RESCUE_EXPIRE}
                self._save_all()
            yield event.plain_result(f"闪避时效已过，{s_name} 自动承受了 {round(dodge_data['pending_dmg'], 2)} 点伤害")
            return
        
        # 成功闪避
        del self.dodge_queue[s_name]
        self._save_all()
        yield event.plain_result(f"✅ {s_name} 成功闪避来自 {dodge_data['source_monster']} 的全部伤害！")

    # ==================== 救援 ====================
    @filter.command(".救援")
    async def cmd_rescue(self, event: AstrMessageEvent):
        """救援濒死员工：.救援 已救回 员工名"""
        args = event.message_str.strip().split()
        if len(args) < 3:
            yield event.plain_result("格式：.救援 已救回 员工名")
            return
        
        target = args[2]
        
        if target not in self.dying_queue:
            yield event.plain_result(f"【{target}】不在濒死列表中")
            return
        
        now = time.time()
        expire_time = self.dying_queue[target]["expire"]
        
        if now > expire_time:
            # 超时，员工永久死亡
            del self.dying_queue[target]
            if target in self.staff_data:
                # 标记为死亡（可以从数据中删除或添加死亡标记）
                self.staff_data[target]["is_dying"] = True
                self.staff_data[target]["is_dead"] = True  # 新增死亡标记
            self._save_all()
            yield event.plain_result(f"💀 救援超时！【{target}】已永久死亡，无法再被救援")
            return
        
        # 救援成功
        staff = self.staff_data[target]
        staff["is_dying"] = False
        staff["hp"] = 1.0
        del self.dying_queue[target]
        self._save_all()
        yield event.plain_result(f"✅ 救援成功！【{target}】脱离濒死状态，当前生命值 1.0")
   
   #====================异想体信息======================
    @filter.command(".异想体信息")
    async def cmd_monster_info(self, event: AstrMessageEvent):
        """查看异想体信息"""
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.异想体信息 异想体名\n完整格式：.异想体信息 异想体名 --showall")
            return
        
        monster_name = args[1]
        show_all = "--showall" in args
        
        if monster_name not in self.monster_lib:
            yield event.plain_result(f"异想体【{monster_name}】不存在")
            return
        
        monster = self.monster_lib[monster_name]
        raid_info = self.raid_status.get(monster_name, {})
        is_raid = raid_info.get("is_raid", False)
        
        msg = f"=====异想体【{monster_name}】=====\n"
        msg += f"编号：{monster.get('code', '未知')}\n"
        
        # 显示计数器（如果有）
        if "q_counter" in monster:
            msg += f"逆卡巴拉计数器：{monster['q_counter']}/{monster.get('q_counter_max', '?')}\n"
        
        if is_raid:
            msg += f"状态：⚠️ 已出逃\n剩余血量：{round(raid_info.get('hp', 0), 2)} / {MONSTER_HP_BASE.get(monster['level'], 4.0)}\n"
        else:
            msg += f"状态：🔒 收容中\n"
        
        if show_all:
            msg += (
                f"\n--- 完整资料 ---\n"
                f"伤害类型：{monster['atk_type']}\n"
                f"评级：{monster['level']}\n"
                f"移动速度：{monster['speed']}\n"
                f"物理抗性：{monster['phy']}\n"
                f"精神抗性：{monster['spi']}\n"
                f"侵蚀抗性：{monster['cor']}\n"
                f"灵魂抗性：{monster['sou']}\n"
            )
        else:
            msg += "\n💡 提示：使用 .异想体信息 异想体名 --showall 查看完整资料"
        
        yield event.plain_result(msg)

    # ==================== 扣除逆卡巴拉计数器 ====================
    @filter.command(".扣除计数器")
    async def cmd_reduce_counter(self, event: AstrMessageEvent):
        """扣除异想体的逆卡巴拉计数器：.扣除计数器 异想体名 [数量]"""
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.扣除计数器 异想体名 [数量]\n例：.扣除计数器 西里安\n例：.扣除计数器 西里安 2")
            return
        
        monster_name = args[1]
        amount = int(args[2]) if len(args) > 2 else 1
        
        if monster_name not in self.monster_lib:
            yield event.plain_result(f"异想体【{monster_name}】不存在")
            return
        
        monster = self.monster_lib[monster_name]
        
        if "q_counter" not in monster:
            yield event.plain_result(f"异想体【{monster_name}】没有逆卡巴拉计数器数据")
            return
        
        old_value = monster["q_counter"]
        new_value = max(0, old_value - amount)
        monster["q_counter"] = new_value
        
        msg = f"【{monster_name}】逆卡巴拉计数器：{old_value} → {new_value}"
        
        # 计数器归零时触发出逃
        if new_value <= 0 and not self.raid_status.get(monster_name, {}).get("is_raid", False):
            # 触发收容突破
            self.raid_status[monster_name] = {
                "is_raid": True,
                "hp": MONSTER_HP_BASE.get(monster["level"], 4.0)
            }
            msg += f"\n⚠️ 逆卡巴拉计数器归零！【{monster_name}】突破收容！"
        
        self._save_all()
        yield event.plain_result(msg)

    #==================恢复计数器========================
    @filter.command(".恢复计数器")
    async def cmd_restore_counter(self, event: AstrMessageEvent):
        """恢复异想体的逆卡巴拉计数器：.恢复计数器 异想体名 [数量]"""
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.恢复计数器 异想体名 [数量]\n例：.恢复计数器 西里安\n例：.恢复计数器 西里安 1")
            return
        
        monster_name = args[1]
        amount = int(args[2]) if len(args) > 2 else 1
        
        if monster_name not in self.monster_lib:
            yield event.plain_result(f"异想体【{monster_name}】不存在")
            return
        
        monster = self.monster_lib[monster_name]
        
        if "q_counter_max" not in monster:
            yield event.plain_result(f"异想体【{monster_name}】没有逆卡巴拉计数器数据")
            return
        
        old_value = monster["q_counter"]
        new_value = min(monster["q_counter_max"], old_value + amount)
        monster["q_counter"] = new_value
        
        msg = f"【{monster_name}】逆卡巴拉计数器：{old_value} → {new_value}"
        
        self._save_all()
        yield event.plain_result(msg)  

    #=========================死亡==========================
    @filter.command(".死亡名单")
    async def cmd_dead_list(self, event: AstrMessageEvent):
        """查看已死亡的员工"""
        dead_staff = [name for name, data in self.staff_data.items() if data.get("is_dead", False)]
        if not dead_staff:
            yield event.plain_result("暂无员工死亡")
        else:
            yield event.plain_result(f"💀 已死亡员工：{dead_staff}")

    @filter.command(".移除死亡")
    async def cmd_remove_dead(self, event: AstrMessageEvent):
        """移除死亡员工：.移除死亡 员工名"""
        args = event.message_str.strip().split()
        if len(args) < 2:
            yield event.plain_result("格式：.移除死亡 员工名")
            return
        
        target = args[1]
        
        if target not in self.staff_data:
            yield event.plain_result(f"员工【{target}】不存在")
            return
        
        if not self.staff_data[target].get("is_dead", False):
            yield event.plain_result(f"【{target}】并未死亡")
            return
        
        del self.staff_data[target]
        self._save_all()
        yield event.plain_result(f"已移除死亡员工【{target}】")


def register():
    return LobFullEgoPlugin