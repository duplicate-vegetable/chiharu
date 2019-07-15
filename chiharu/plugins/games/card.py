import random
import json
import itertools
import functools
from enum import IntEnum
import contextlib
import os
from typing import Dict, Iterable, Tuple, Awaitable, List
from datetime import date
import chiharu.plugins.config as config
from nonebot import on_command, CommandSession, get_bot, permission
from nonebot.command import call_command
config.logger.open('card')

# -game card 引导至card的指令列表
# √抽卡指令（参数：卡池，张数） 参数为空时引导至查看卡池 限额抽完时引导至查看个人信息 再次输入确认使用资源抽卡
# √查看卡池指令（参数：卡池或空） 引导抽卡指令 查看具体卡池 引导至私聊卡池信息
# 添加卡指令（参数：卡名，张数） 引导至查看卡池
# 查看个人信息，包含资源数，仓库量，剩余免费抽卡次数（级别？） 引导至查看库存与创造卡与留言簿
# 查看库存指令（翻页） 引导至分解卡与创造卡
# 仓储操作指令，包含加入特别喜欢，加入愿望单
# 分解卡指令
# 留言簿指令
# √批量添加指令
# 查看审核指令
# 审核通过指令
# 预约开放活动卡池指令
# 维护？
# status: 1 已开放 0 已结束 2 未开始 3 已空

def to_byte(num):
    return bytes([num // 256, num % 256])
guide = {'draw': '使用-card.draw 卡池id/名字 抽卡次数 进行抽卡，\n-card.draw5 卡池id/名字 直接进行五连抽卡',
    'check_detail': '私聊-card.check 卡池id/名字 查询卡池具体信息（刷屏预警）',
    'check': '-card.check 不带参数 查询卡池列表',
    'info': '-xxxxxx 查看个人信息'
}

with open(config.rel(r"games\card\pool"), 'rb') as f:
    pool = list(itertools.starmap(lambda x, y: int(x) * 256 + int(y), config.group(2, f.read())))
with open(config.rel(r"games\card\card_info.json"), encoding='utf-8') as f:
    card_info = json.load(f)
with open(config.rel(r"games\card\daily_pool.json"), encoding='utf-8') as f:
    daily_pool_all = json.load(f)
    daily_pool = list(filter(lambda x: x['status'] == 1 or x['status'] == 3, daily_pool_all))
    daily_pool_draw = list(map(lambda x: x['cards'], daily_pool))
def save_card_info():
    with open(config.rel(r"games\card\card_info.json"), 'w', encoding='utf-8') as f:
        f.write(json.dumps(card_info, ensure_ascii=False, indent=4, separators=(',', ': ')))
def save_pool():
    with open(config.rel(r"games\card\pool"), 'wb') as f:
        f.write(bytes(itertools.chain(*map(lambda x: [x // 256, x % 256], pool))))
def save_daily_pool():
    with open(config.rel(r"games\card\daily_pool.json"), 'w', encoding='utf-8') as f:
        f.write(json.dumps(daily_pool_all, ensure_ascii=False, indent=4, separators=(',', ': ')))

def get_card_names(*l):
    return '，'.join([card_info[i]['name'] for i in l])
def daily_pool_find(s):
    l = list(filter(lambda x: x['name'] == s or str(x['id']) == s, daily_pool))
    if len(l) == 0:
        return None
    return l[0]

class user_info:
    def __init_subclass__(cls, path, if_binary=False):
        cls.path_all = config.rel(path)
        cls.if_binary = if_binary
    def __init__(self, index):
        self.path = self.path_all % index
        try:
            self.file = open(self.path, 'r+b' if self.if_binary else 'r+')
        except FileNotFoundError:
            self.init_begin()
    def __del__(self):
        self.file.close()
class user_storage(user_info, path=r"games\card\user_storage\%i", if_binary=True):
    def init_begin(self):
        self.file = open(self.path, 'x+b' if self.if_binary else 'x+')
        self.file.write(bytes([0, 0, 10, 0]))
    def check(self):
        if os.stat(self.path).st_size < 4 * len(pool) + 4:
            self.file.seek(0, 2)
            self.file.write(bytes(map(lambda x: 0, range(4 * len(pool) + 4 - os.stat(self.path).st_size))))
            self.file.flush()
    def read_info(self):
        # 4 byte data for user info
        self.file.seek(0)
        a, b, c, d = self.file.read(4)
        return {'money': a * 256 + b, 'confirm': bool(c & 128), 'time': c % 128}
    def save_info(self, val):
        self.file.seek(0)
        self.file.write(bytes([val['money'] // 256, val['money'] % 256, val['confirm'] * 128 + val['time'], 0]))
    def read(self, id):
        # 4 byte data for each card
        self.check()
        self.file.seek(4 * id + 4)
        a, b, c, d = self.file.read(4)
        return {'num': a * 256 + b, 'fav': bool(d & 2), 'wish': bool(d & 1)}
    def save(self, id, dct):
        self.file.seek(4 * id + 4)
        self.file.write(bytes([dct['num'] // 256, dct['num'] % 256, 0, dct['fav'] * 2 + dct['wish']]))
    def give(self, *args) -> Dict[str, List[int]]:
        self.check()
        ret = {'max': [], 'wish_reset': []}
        for i in args:
            data = self.read(i)
            data['num'] += 1
            # 超过上限
            if data['num'] >= 65536:
                data['num'] -= 1
                ret['max'].append(i)
            # 抽到首张时取消愿望单，并加入特别喜欢
            if data['num'] == 1 and data['wish']:
                data['wish'] = False
                data['fav'] = True
                ret['wish_reset'].append(i)
            self.save(i, data)
        return ret
class user_create(user_info, path=r"games\card\user_create\%i.txt"):
    pass
@contextlib.contextmanager
def open_user_create(qq, operate='r'):
    resource = user_create(qq, operate)
    try:
        yield resource
    finally:
        del resource
@contextlib.contextmanager
def open_user_storage(qq):
    resource = user_storage(qq)
    try:
        yield resource
    finally:
        del resource
#with open_user_storage(qq) as f:
#    f.give(id, id)

def _des(l, if_len=True, max=3):
    if len(l) > max:
        return '，'.join(map(lambda x: card_info[x]['name'], random.sample(l, k=max))) + f'等{len(l)}种' if if_len else ''
    else:
        return '，'.join(map(lambda x: card_info[x]['name'], l))
def pool_des(pool_info: Dict):
    title = {'event': '活动卡池', 'daily': '每日卡池', 'new': '新卡卡池'}
    not_zero = list(filter(lambda x: pool[x] > 0, pool_info['cards']))
    only_one = list(filter(lambda x: pool[x] == 1, pool_info['cards']))
    num = functools.reduce(lambda x, y: x + y, map(lambda x: pool[x], pool_info['cards']))
    return f"""{title[pool_info['type']]}{f'''：{pool_info['name']} id：{pool_info['id']}
{pool_info['description']} {pool_info['end_date']} 截止''' if pool_info['type'] == 'event' else ''}
包含{_des(not_zero)}共{num}张。{f'''
{_des(only_one)}只余一张！''' if len(only_one) != 0 else ''}"""
def pool_des_detail(pool_info: Dict):
    title = {'event': '活动卡池', 'daily': '每日卡池', 'new': '新卡卡池'}
    not_zero = list(filter(lambda x: pool[x] > 0, pool_info['cards']))
    return f"""{title[pool_info['type']]}{f'''：{pool_info['name']} id：{pool_info['id']}
{pool_info['description']} {pool_info['end_date']} 截止''' if pool_info['type'] == 'event' else ''}
包含卡牌：{'，'.join(map(lambda x: f'''{card_info[x]['name']}x{pool[x]}''', not_zero))}"""

def center_card(*args):
    return ""

def add_cardname(names, num=0, **kwargs):
    global card_info, pool
    with open(config.rel(r"games\card\pool"), 'ab') as f:
        for name in names:
            card_info.append(dict(name=name, id=len(card_info), **kwargs))
            pool.append(num)
            f.write(to_byte(num)) # 每个卡最多65535张
    save_card_info()
def add_card(arg: Iterable[Tuple[int, int]]):
    global pool
    with open(config.rel(r"games\card\pool"), 'rb+') as f:
        for id, num in arg:
            f.seek(2 * id)
            pool[id] += num
            f.write(to_byte(pool[id]))

@on_command(('card', 'draw'), only_to_me=False, aliases=('抽卡'))
@config.ErrorHandle
@config.maintain('card')
async def card_draw(session: CommandSession):
    if session.get('name') is None:
        # 卡池介绍
        await session.send('\n\n'.join(map(lambda x: pool_des(x), daily_pool)) + '\n\n' + guide['draw'], auto_escape=True)
    else:
        qq = session.ctx['user_id']
        name, num = session.get('name'), session.get('num')
        if num > 5 or num <= 0:
            await session.send('一次最多五连抽卡！')
            return
        p = daily_pool_find(name)
        if p is None:
            await session.send('未发现此卡池\n' + guide['draw'])
        elif p['status'] == 3:
            await session.send('卡池已空，无法继续抽取')
        else:
            config.logger.card << f'【LOG】用户{qq} 于卡池{p["id"]} 进行{num}次抽卡'
            with open_user_storage(qq) as f:
                data = {'empty': False, 'payed': False, 'money': 0}
                info = f.read_info()
                weight = list(map(lambda x: pool[x], p['cards']))
                pool_num = functools.reduce(lambda x, y: x + y, weight)
                if pool_num <= num:
                    num = pool_num
                    data['empty'] = True
                if info['time'] == 0:
                    if not info['confirm']:
                        if info['money'] >= 100:
                            info['confirm'] = True
                            f.save_info(info)
                            await session.send(f'您今日的免费10次抽卡次数已用尽，是否确认使用en进行抽卡？再次输入抽卡指令确认\n{guide["info"]}') # 取消确认？？？ TODO
                            config.logger.card << f'【LOG】用户{qq} 免费抽卡次数已用尽 可以使用en进行抽卡'
                        else:
                            await session.send(f'您今日的免费10次抽卡次数已用尽\n{guide["info"]}')
                            config.logger.card << f'【LOG】用户{qq} 免费抽卡次数已用尽'
                        return
                    else:
                        if info['money'] >= 100 * num:
                            info['money'] -= 100 * num
                            data['payed'] = True
                            data['money'] = info['money']
                            f.save_info(info)
                        else:
                            await session.send(f'您剩余en已不足\n\n您还有{info["money"]}en，每100en可以抽一张卡\n{guide["info"]}')
                            config.logger.card << f'【LOG】用户{qq} en数不足'
                            return
                elif info['time'] < num:
                    await session.send(f'您今日的免费10次抽卡次数不足，只剩{info["time"]}次\n{guide["info"]}')
                    config.logger.card << f'【LOG】用户{qq} 免费抽卡次数不足'
                    return
                else:
                    info['time'] -= num
                    f.save_info(info)
                if data['empty']:
                    def _f():
                        for id, n in zip(p['cards'], weight):
                            for i in range(n):
                                pool[id] -= 1
                                yield id
                    p['status'] = 3
                    save_daily_pool()
                else:
                    def _f():
                        for i in range(num):
                            index = random.choices(range(len(p['cards'])), weight)[0]
                            weight[index] -= 1
                            pool[p['cards'][index]] -= 1
                            yield p['cards'][index]
                get = list(_f())
                ret = f.give(*get)
            await session.send(f"""{'''您已把卡池抽空！
''' if data['empty'] else ''}恭喜您抽中：
{get_card_names(*get)}{f'''
库存 {get_card_names(*ret['max'])} 已达到上限''' if len(ret['max']) != 0 else ''}{f'''
{get_card_names(*ret['wish_reset'])} 已自动取消愿望单''' if len(ret['wish_reset']) != 0 else ''}{f'''
您还剩余{data['money']}en''' if data['payed'] else ''}""")
            if data['payed']:
                config.logger.card << f'【LOG】用户{qq} 消耗了{100 * num}en 剩余{data["money"]}en'
            else:
                config.logger.card << f'【LOG】用户{qq} 剩余{info["time"]}次免费抽取机会'
            config.logger.card << f'【LOG】用户{qq} 获得卡片{get}'
            if len(ret['max']) != 0:
                config.logger.card << f'【LOG】用户{qq} 卡片{ret["max"]}已达到上限'
            if len(ret['wish_reset']) != 0:
                config.logger.card << f'【LOG】用户{qq} 愿望单内{ret["wish_reset"]}已被自动取消'
            if data['empty']:
                config.logger.card << f'【LOG】卡池{p["id"]}已空'

@card_draw.args_parser
@config.ErrorHandle
async def _(session: CommandSession):
    if session.current_arg_text == "":
        session.state['name'] = None
    else:
        l = session.current_arg_text.strip().split(' ')
        if len(l) == 1:
            session.state['name'] = l[0]
            session.state['num'] = 1
        else:
            session.state['name'] = l[0]
            session.state['num'] = int(l[1])

@on_command(('card', 'draw5'), aliases=('五连抽卡',), only_to_me=False)
@config.ErrorHandle
@config.maintain('card')
async def card_draw_5(session: CommandSession):
    if session.current_arg_text == "":
        await call_command(get_bot(), session.ctx, ('card', 'draw'), current_arg="")
    else:
        await call_command(get_bot(), session.ctx, ('card', 'draw'), current_arg=session.current_arg_text.strip() + ' 5')

@on_command(('card', 'check'), only_to_me=False)
@config.ErrorHandle
@config.maintain('card')
async def card_check(session: CommandSession):
    if session.current_arg_text == "":
        await session.send('\n\n'.join(map(lambda x: pool_des(x), daily_pool)) + f'\n\n{guide["draw"]}\n{guide["check_detail"]}', auto_escape=True)
    else:
        p = daily_pool_find(session.current_arg_text)
        if p is None:
            await session.send('未发现此卡池')
        else:
            await session.send(pool_des_detail(find[0]) + f'\n\n{guide["draw"]}\n{guide["check"]}', auto_escape=True)

@on_command(('card', 'add'), only_to_me=False)
@config.ErrorHandle
@config.maintain('card')
async def card_add(session: CommandSession):
    pass

@on_command(('card', 'add_group'), only_to_me=False, permission=permission.SUPERUSER)
@config.ErrorHandle
async def card_add_group(session: CommandSession):
    lst = session.current_arg_text.split('\n')
    group = lst[0].strip()
    num = int(lst[-1])
    if num >= 65536:
        await session.send(">65536")
        return
    add_cardname(map(lambda x: x.strip(), lst[1:-1]), num=num, group=group)
    await session.send("successfully added cards")
    config.logger.card << f'【LOG】卡池新增{group}卡组共{len(lst) - 2}种，每种{num}张'

@on_command(('card', 'check_valid'), only_to_me=False, permission=permission.SUPERUSER)
@config.ErrorHandle
async def card_valid(session: CommandSession):
    pass