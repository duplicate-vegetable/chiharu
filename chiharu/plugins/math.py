import itertools
import math
import requests
import re
import asyncio
import functools
import datetime
import getopt
from wand.image import Image
from wand.drawing import Drawing
from wand.color import Color
import chiharu.plugins.config as config
from nonebot import on_command, CommandSession, get_bot, permission
import os
import json

async def latex(s, hsh=()):
    loop = asyncio.get_event_loop()
    ipt = re.sub('\+', '%2B', s)
    url = await loop.run_in_executor(None, functools.partial(requests.get,
        'https://www.zhihu.com/equation?tex=' + ipt,
        headers={'user-agent': config.user_agent}))
    name = str(hash((s,) + hsh))
    with open(config.img(name + '.svg'), 'wb') as f:
        f.write(url.content)
    with Image(filename=config.img(name + '.svg')) as image:
        with image.convert('png') as converted:
            converted.background_color = Color('white')
            converted.alpha_channel = 'remove'
            converted.save(filename=config.img(name + '.png'))
    return name + '.png'

@on_command(('tools', 'Julia'), only_to_me=False)
@config.description("绘制Julia集。", ("x y"))
@config.ErrorHandle
async def Julia(session: CommandSession):
    """绘制以c=x+yi为参数，z→z^2+c的Julia集。
    Julia集为在复平面上，使得无限迭代z→z^2+c不发散的初值z_0的集合。
    Ref：https://en.wikipedia.org/wiki/Julia_set"""
    c = session.current_arg_text.split(' ')
    if len(c) != 2:
        await session.send("使用格式：-tools.Julia x y\n绘制Julia set，使得c=x+yi")
        return
    x = float(c[0])
    y = float(c[1])
    height = 600
    dx = 0.005
    MAX = 80
    color_in = (128, 48, 10)
    name = 'Julia_%f_%f.png' % (x, y)
    if not os.path.exists(config.img(name)):
        f = lambda i, x: math.log(i + math.log(abs(x) + 3) + 2)
        await session.send("少女计算中...请耐心等待...")
        with Drawing() as draw:
            for x1, y1 in itertools.product(range(height), range(height)):
                x2, y2 = (x1 - height / 2) * dx, (y1 - height / 2) * dx
                for i in range(MAX):
                    x3, y3 = (x2 ** 2 - y2 ** 2 + x, 2 * x2 * y2 + y)
                    if (x2 - x3) ** 2 + (y2 - y3) ** 2 >= 100:
                        break
                    x2, y2 = x3, y3
                else:
                    i += 1
                r2 = math.sqrt(x2 ** 2 + y2 ** 2)
                color = tuple(map(lambda c: c[0] * c[1], zip(color_in, (f(i, x2), f(i, y2), f(i, r2)))))
                draw.fill_color = Color('rgb(%i, %i, %i)' % color)
                draw.point(x1, y1)
            with Image(width=height, height=height) as image:
                draw(image)
                image.save(filename=config.img(name))
    await session.send(config.cq.img(name))

@on_command(('tools', 'Mandelbrot'), only_to_me=False)
@config.description("绘制Mandelbrot集。", ("x y"), hide=True)
@config.ErrorHandle
async def Mandelbrot(session: CommandSession):
    """绘制以z_0=x+yi为初值，z→z^2+c的Mandelbrot集。
    Mandelbrot集为在复平面上，使得无限迭代z→z^2+c不发散的参数c的集合。
    Ref：https://en.wikipedia.org/wiki/Mandelbrot_set"""
    c = session.current_arg_text.split(' ')
    if len(c) != 2:
        await session.send("使用格式：-tools.Mandelbrot x y\n绘制Mandelbrot set，使得z0=x+yi")
        return
    x = float(c[0])
    y = float(c[1])
    height = 600
    dx = 0.005
    MAX = 80
    color_in = (128, 48, 10)
    name = 'Mandelbrot_%f_%f.png' % (x, y)
    if not os.path.exists(config.img(name)):
        f = lambda i, x: math.log(i + math.log(abs(x) + 3) + 2)
        await session.send("少女计算中...请耐心等待...")
        with Drawing() as draw:
            for x1, y1 in itertools.product(range(height), range(height)):
                x2, y2 = (x1 - height / 2) * dx, (y1 - height / 2) * dx
                x4, y4 = x, y
                for i in range(MAX):
                    x3, y3 = (x4 ** 2 - y4 ** 2 + x2, 2 * x4 * y4 + y2)
                    if (x4 - x3) ** 2 + (y4 - y3) ** 2 >= 100:
                        break
                    x4, y4 = x3, y3
                else:
                    i += 1
                r4 = math.sqrt(x4 ** 2 + y4 ** 2)
                color = tuple(map(lambda c: c[0] * c[1], zip(color_in, (f(i, x4), f(i, y4), f(i, r4)))))
                draw.fill_color = Color('rgb(%i, %i, %i)' % color)
                draw.point(x1, y1)
            with Image(width=height, height=height) as image:
                draw(image)
                image.save(filename=config.img(name))
    await session.send(config.cq.img(name))

@on_command(('tools', 'oeis'), only_to_me=False)
@config.ErrorHandle
async def oeis(session: CommandSession):
    """查询oeis（整数序列在线百科全书）。
    参数为序列中的几项，使用逗号分隔。或为oeis编号如A036057。"""
    if re.match('A\d+', session.current_arg_text):
        result = await oeis_id(session.current_arg_text)
        if type(result) == str:
            await session.send(result)
        else:
            await session.send('%s\nDESCRIPTION: %s\n%s\nEXAMPLE: %s' % \
                    (result['Id'], result['description'], result['numbers'], result['example']))
    elif re.fullmatch('(-?\d+, ?)*-?\d+', session.current_arg_text):
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, requests.get,
                'http://oeis.org/search?q=' + session.current_arg_text + '&sort=&language=&go=Search')
        if response.status_code != 200:
            await session.send('sequence not found!')
            return
        match = re.search('A\d+', response.text)
        if not match:
            await session.send('sequence not found!')
            return
        s = match.group()
        result = await oeis_id(s)
        if type(result) == str:
            await session.send(result)
        else:
            await session.send('%s\nDESCRIPTION: %s\n%s\nEXAMPLE: %s' % \
                    (result['Id'], result['description'], result['numbers'], result['example']))
    else:
        await session.send("I don't know what you mean.")

async def oeis_id(s):
    loop = asyncio.get_event_loop()
    try:
        response = await asyncio.wait_for(loop.run_in_executor(None, requests.get,
            'http://oeis.org/' + s), timeout=600.0)
    except asyncio.TimeoutError:
        return "time out!"
    if response.status_code != 200:
        return 'Name not found!'
    text = response.text
    begin_pos = 0
    match = re.search('<title>(A\d+)', text[begin_pos:])
    if not match:
        return 'Title not found!'
    begin_pos += match.span()[1]
    Id = match.group(1)
    match = re.search('<td valign=top align=left>\n(.*)\n', text[begin_pos:])
    if not match:
        return 'Description not found!'
    begin_pos += match.span()[1]
    description = match.group(1).strip()
    match = re.search('<td width="710">', text[begin_pos:])
    if not match:
        return 'Numbers not found!'
    begin_pos += match.span()[1]
    match = re.search('<tt>(.*?)</tt>', text[begin_pos:])
    if not match:
        return 'Numbers not found!'
    numbers = match.group(1)
    match = re.search('EXAMPLE', text[begin_pos:])
    if not match:
        example = None
    else:
        example_pos = begin_pos + match.span()[1]
        match2 = re.search('<font size=', text[example_pos:])
        match3 = re.search('</table>', text[example_pos:])
        if not match2:
            match2 = match3
        if not match3:
            example = None
        else:
            example_end = example_pos + match2.span()[1]
            example_list = []
            while 1:
                match2 = re.search('<tt>(.*)</tt>', text[example_pos:example_end])
                if not match2:
                    break
                example_pos += match2.span()[1]
                example_list.append(re.sub('&nbsp;', '\t', re.sub('<.*?>', '', match2.group(1))).strip())
            example = '\n'.join(example_list)
    result = {'Id': Id, 'description': description, 'numbers': numbers, 'example': example}
    return result

@on_command(('tools', 'quiz'), only_to_me=False, shell_like=True)
@config.description("每月趣题。", ("[-t YYYYMM]", "[-a]"))
@config.ErrorHandle
async def quiz(session: CommandSession):
    """每月趣题。
    可用选项：
        -t, --time 接六位月份码查看历史趣题。
        -a, --answer 查看答案。
    欢迎提交好的东方化（或其他IP化也欢迎~）的趣题至维护者邮箱shedarshian@gmail.com（难度至少让维护者能看懂解答）"""
    opts, args = getopt.gnu_getopt(session.args['argv'], 't:a', ['time=', 'answer'])
    d = datetime.date.today()
    s, ans = None, False
    for o, a in opts:
        if o in ('-t', '--time'):
            s = a
            if not re.match('\d{6+}', s):
                await session.send('请使用YYYYMM（四位年份加两位月份）来获取往年试题')
                return
            if int(s[0:4]) > d.year or int(s[0:4]) == d.year and int(s[4:6]) > d.month:
                await session.send('未发现该月题目，题目自201910开始')
                return
        elif o in ('-a', '--answer'):
            ans = True
    if s is None:
        s = f'{d.year}{d.month:02}'
    try:
        print(s)
        with open(config.rel("games\\quiz.json"), encoding='utf-8') as f:
            await session.send(json.load(f)["math"][s][int(ans)], ensure_private=ans)
    except KeyError:
        await session.send('未发现该月题目，题目自201910开始')

@on_command(('tools', 'quiz_submit'), only_to_me=False, shell_like=True)
@config.ErrorHandle
async def quiz_submit(session: CommandSession):
    """提交每月趣题答案。"""
    for group in config.group_id_dict['aaa']:
        await get_bot().send_group_msg(group_id=group, message=f'用户{session.ctx["user_id"]} 提交答案：\n{session.current_arg}', auto_escape=True)
    await session.send('您已成功提交答案')
