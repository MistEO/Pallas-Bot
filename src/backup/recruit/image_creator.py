import re
import os
import datetime

from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def create_recruit_image(recruit_info):
    text = ''
    for tags, operators, rank in recruit_info:
        if rank < 1:
            continue
        rank += 3
        
        star_text = '[cl ['
        for tag in tags:
            star_text += ' ' + tag + ' '
        star_text += ']  ' + (str)(rank) + ' ★@#174CC6 cle]'

        text += '\n\n'
        text += star_text

        last_r = 0
        for op in operators:
            name = op[0]
            r = op[1] + 1
            if r != last_r:
                stars = ''
                for i in range(r):
                    stars += '★'
                text += '\n\n['
                if r == 6:
                    text += f'[cl {stars}@#FF4343 cle]'
                elif r == 5:
                    text += f'[cl {stars}@#FEA63A cle]'
                elif r == 4:
                    text += f'[cl {stars}@#A288B5 cle]'
                else:
                    text += stars

                text += '] '
            last_r = r
            text += ' ' + name + ' '
        text += '\n\n'
    print(text)
    if not len(text):
        return False

    return create_image('伟大的战士们啊，我会在你们身边，与你们一同奋勇搏杀。\n' + text)


class TextParser:
    def __init__(self, text: str, color='#000000', font_size=16, max_seat=560):
        self.font = ImageFont.truetype(font_file, font_size)
        self.text = text
        self.color = color
        self.max_seat = max_seat
        self.char_list = []
        self.line = 0

        self.__parse()

    def __parse(self):
        text = self.text.strip('\n')
        search = re.findall(r'\[cl\s(.*?)@#(.*?)\scle]', text)

        color_pos = {0: self.color}

        for item in search:
            temp = f'[cl {item[0]}@#{item[1]} cle]'
            index = text.index(temp)
            color_pos[index] = f'#{item[1]}'
            color_pos[index + len(item[0])] = self.color
            text = text.replace(temp, item[0], 1)

        length = 0
        sub_text = ''
        cur_color = self.color
        for idx, char in enumerate(text):
            if idx in color_pos:
                if cur_color != color_pos[idx] and sub_text:
                    self.__append_row(cur_color, sub_text, enter=False)
                    sub_text = ''
                cur_color = color_pos[idx]

            length += self.__font_seat(char)[0]
            sub_text += char

            is_end = idx == len(text) - 1
            if length >= self.max_seat or char == '\n' or is_end:
                enter = True
                if not is_end:
                    if text[idx + 1] == '\n' and sub_text != '\n' and sub_text[-1] != '\n':
                        enter = False

                self.__append_row(cur_color, sub_text, enter=enter)
                sub_text = ''
                length = 0

    def __append_row(self, color, text, enter=True):
        if enter:
            self.line += 1
        self.char_list.append(
            (enter, color, text, *self.__font_seat(text))
        )

    def __font_seat(self, char):
        return self.font.getsize_multiline(char)

    @staticmethod
    def char_seat(char):
        return 0.58 if 32 <= ord(char) <= 126 else 1

    @staticmethod
    def cut_code(code, length):
        code_list = re.findall('.{' + str(length) + '}', code)
        code_list.append(code[(len(code_list) * length):])
        res_list = []
        for n in code_list:
            if n != '':
                res_list.append(n)
        return res_list


# temp_dir = 'log/message'
font_file = 'bot/plugins/recruit/AdobeHeitiStd-Regular.otf'
# logo_file = 'resource/style/rabbit.png'
# logo_file_white = 'resource/style/rabbit-white.png'

line_height = 16
side_padding = 10


def create_image(text: str, images=None, font_size=16):
    text = TextParser(text, font_size=font_size)

    height = text.line + 2
    image = Image.new('RGB', (600, height * line_height), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    font = text.font

    col = side_padding
    row = 0
    for line, item in enumerate(text.char_list):
        draw.text((col, side_padding + row * line_height), item[2], font=font, fill=item[1])
        col += item[3]
        if item[0]:
            row += 1
            col = side_padding

    # icon = Image.open(logo_file)
    # icon = icon.resize(size=(30, 30))
    # image.paste(icon, box=(570, 0), mask=icon)

    if images:
        for item in images:
            if os.path.exists(item['path']) is False:
                continue
            img = Image.open(item['path']).convert('RGBA')

            pos = list(item['pos'])
            height = item['size']
            width = int(height * (img.width / img.height))
            offset = (height - width) / 2
            if offset:
                pos[0] += int(offset)

            img = img.resize(size=(width, height))
            image.paste(img, box=tuple(pos), mask=img)

    bio = BytesIO()
    image.save(bio, format="PNG")
    return bio.getvalue()