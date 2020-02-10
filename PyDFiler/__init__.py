import dateparser
import datetime
import subprocess
import os

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from os import path

import Config
from GrafanaAPI import *

class PyDFiler:

    def __init__(self):
        self.api = GrafanaAPI(api_key=Config.Grafana.api_key, server_address=Config.Grafana.address)

    def generate_PDF_from_dashboard(self, dashboard_uuid, output_folder, range_time_from='now-1d', range_time_to='now', output_pdf=Config.wkhtmltopdf.output_pdf, print_title=False):
        panel_title = self.api.get_panel_id(dashboard_uuid)
        panel_images_all_rgb = self.render_panel_images_to_rgb(dashboard_uuid, range_time_from, range_time_to)
        crop_area = (0, 30, Config.Default.Image.width, Config.Default.Image.height)
        cropped_images_rgb = self.crop_images_rgb(panel_images_all_rgb, crop_area)
        collage_width, collage_height = self.calculate_collage_size(cropped_images_rgb)

        if print_title:
            for panel_id in cropped_images_rgb.keys():
                self.draw_text_on_image(cropped_images_rgb[panel_id], panel_title[panel_id])

        number_of_images = len(cropped_images_rgb)

        dimensions = self.calculate_collage_dimensions(number_of_images)
        collage_width_final = int(collage_width / dimensions[0])
        collage_height_final = int(collage_height / dimensions[1])

        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        #self.create_collage_from_files(width=collage_width_final, height=collage_height_final, list_of_image_paths=saved_file_paths,col=dimensions[1], row=dimensions[0])
        collage_output_path = output_folder / 'collage.png'
        collage_path = self.create_collage_from_dict(width=collage_width_final, height=collage_height_final, images_dict=cropped_images_rgb, collage_output_path=collage_output_path, col=dimensions[1], row=dimensions[0])

        time_from = str(dateparser.parse(range_time_from))
        time_from = self.strip_datetime_to_minutes(time_from)

        time_to = str(dateparser.parse(range_time_to))
        time_to = self.strip_datetime_to_minutes(time_to)

        dashboard_info = {
                '$_DOCUMENT_TITLE': self.get_dashboard_title(dashboard_uuid),
                '$_TIME_FROM': time_from,
                '$_TIME_TO': time_to
            }
        html_output_dir = Path(output_folder)
        html_output_path = str(self.generate_html_from_template(output_dir=html_output_dir, replace_dict=dashboard_info))
        print(f'html_out_path = {html_output_path}')

        pdf_output_path = output_folder / 'raport.pdf'
        pdf_path = self.render_pdf_from_html(input_html=html_output_path, output=pdf_output_path.__str__())

        return pdf_path


    def render_panel_images_to_rgb(self, dashboard_uuid, time_range_from, time_range_to):
        '''

        :return: dict() of { panel_id : image_rgb }
        '''

        panel_data = self.api.get_panel_id(dashboard_uuid)
        panel_ids = panel_data.keys()

        image_dict_rgb = dict()

        for panel_id in panel_ids:
            url = self.api.panel_image_url(dashboard_uuid, panel_id, time_range_from=time_range_from, time_range_to=time_range_to)
            headers = self.api.headers
            print(f'Fetching panel: {panel_id} from: {url}')
            image_raw = requests.get(url=url, headers=headers)
            image_b = Image.open(BytesIO(image_raw.content))
            image_rgb = Image.new('RGB', image_b.size, (255, 255, 255))
            image_rgb.paste(image_b, mask=image_b.split()[3])
            image_dict_rgb[panel_id] = image_rgb

        return image_dict_rgb

    def crop_images_rgb(self, image_dict_rgb, crop_area=(0, 30, Config.Default.Image.width, Config.Default.Image.height)):
        '''

        :param image_dict_rgb: image dict as generated by the render_panel_images_to_rgb()
        :return: cropped_image_dict: { panel_id : cropped_image }
        '''

        image_dict_keys = image_dict_rgb.keys()

        cropped_image_dict = dict()

        for panel_id in image_dict_keys:
            cropped_image = self.crop_image_rgb(image_dict_rgb[panel_id],crop_area)
            cropped_image_dict[panel_id] = cropped_image

        return cropped_image_dict

    def render_pdf_from_html(self, wkhtmltopdf_path = Config.wkhtmltopdf.path, input_html=Config.wkhtmltopdf.input_html, output=Config.wkhtmltopdf.output_pdf):
        try:
            print(f'input: {input_html}')
            print(f'output: {output}')
            subprocess.call([wkhtmltopdf_path, input_html, output])
            '''
            subprocess.call([wkhtmltopdf_path, '-T', '0', '-B', '0', '--page-width', '310mm', '--page-height',
                             '800px', 'cover', input, output])
            '''
            print(f'PDF saved to: {output}')
            return output
        except Exception as ex:
            print(ex)

    def create_collage_from_dict(self, width, height, images_dict, collage_output_path=Config.Default.Collage.path, col = 4, row = 4):
        columns = col
        rows = row
        thumbnail_width = width // columns
        thumbnail_height = height // rows
        size = thumbnail_width, thumbnail_height
        new_im = Image.new('RGB', (width, height), 'white')
        images_list = list()

        for panel_id in images_dict.keys():
            images_dict[panel_id].thumbnail(size)
            images_list.append(images_dict[panel_id])

        i = 0
        x = 0
        y = 0
        try:
            for col in range(columns):
                for row in range(rows):
                    new_im.paste(images_list[i], (x, y))
                    i += 1
                    y += thumbnail_height + 2
                x += thumbnail_width + 1
                y = 0
        except Exception as ex:
            print(ex)

        new_im.save(collage_output_path)
        print(f'Image of collage saved to: {collage_output_path}')

        return collage_output_path

    def create_collage_from_files(self, width, height, list_of_image_paths, output_file_path=Config.Default.Collage.path, col = 4, row = 4):
        columns = col
        rows = row
        thumbnail_width = width // columns
        thumbnail_height = height // rows
        size = thumbnail_width, thumbnail_height
        new_im = Image.new('RGB', (width, height), 'white')
        ims = []
        for p in list_of_image_paths:
            im = Image.open(p)
            im.thumbnail(size)
            ims.append(im)
        i = 0
        x = 0
        y = 0
        try:
            for col in range(columns):
                for row in range(rows):
                    #print(i, x, y)
                    new_im.paste(ims[i], (x, y))
                    i += 1
                    y += thumbnail_height + 2
                x += thumbnail_width + 1
                y = 0
        except Exception as ex:
            print(ex)

        new_im.save(output_file_path)
        print(f'Image of collage saved to: {output_file_path}')

    def save_image_to_file(self, image, image_name, dest):
        image_path = dest / image_name
        try:
            image.save(image_path)
            return image_path
        except Exception as ex:
            print(ex)

    def save_images_to_file(self, image_dict_rgb, dest):
        '''

        :param image_dict_rgb: dict() with images in PIL.Image(RGB) format
        :param dest: destination folder
        :return: list() of strings with path of saved files
        '''
        lp = 0
        image_path_list = list()

        for panel_id in image_dict_rgb.keys():
            image_name = f'pic_{str(lp)}.png'
            image_path = dest / image_name
            image_dict_rgb[panel_id].save(image_path)
            lp += 1
            image_path_list.append(image_path)

        return image_path_list

    def crop_image_from_file(self, orig_image_path, crop_area = (0, 0, 0, 0)):
        '''
        :param orig_image_path: Path()
        :param area: (start_x, start_y, end_x, end_y)
        :return: cropped image RGB
        '''
        try:
            orig_image_path = Path(orig_image_path)
            img = Image.open(orig_image_path)
            orig_file_name = str(orig_image_path).split("\\")[-1]
            cropped_img = img.crop(crop_area)
            return cropped_img
        except Exception as ex:
            print(f'Cropping image failed: {ex}')

    def crop_image_rgb(self, image_rgb, crop_area=(0,0,0,0)):
        '''

        :param image_rgb: image in PIL.Image(RGB) format
        :param crop_area: (start_x, start_y, end_x, end_y)
        :return: cropped image in PIL.Image(RGB) format
        '''
        try:
            img = image_rgb
            cropped_img = img.crop(crop_area)
            return cropped_img
        except Exception as ex:
            print(f'Cropping image failed: {ex}')

    def generate_html_from_template(self, output_dir, template_path=Config.Default.Template.dashboard, replace_dict=None):

        if replace_dict is None:
            replace_dict = {
                '$_DOCUMENT_TITLE': 'tytuł dokumentu',
                '$_TIME_FROM': 'czas from',
                '$_TIME_TO': 'czas from'
            }

        personalized_html = ''

        try:
            with open(template_path, 'r') as template:
                template_content = template.read()
                personalized_html = self.replace_values_in_string(template_content, replace_dict)
                template.close()

            output_file = output_dir / 'index.html'
            with open(output_file, 'w') as out_f:
                out_f.write(personalized_html)
                out_f.close()

            return output_file

        except Exception as ex:
            print(ex)

    def replace_values_in_string(self, source: str, replace_by: dict = {}):
        '''

        :param source: source string which is going to be modified
        :param replace_by: dict()
        :return: source string in which dict() key variables will be replaced with values.
        '''
        replaced_string = source
        for variable in replace_by.keys():
            replaced_string = replaced_string.replace(variable, replace_by[variable])

        return replaced_string

    def calculate_collage_dimensions(self, number_of_images:int):
        '''
        lazy implementation of trial division https://en.wikipedia.org/wiki/Trial_division
        :param number_of_images: number of total images in the dict (int)
        :return: pair of two ints - x and y dimension
        '''
        dimensions = []
        n = number_of_images
        while n % 2 == 0:
            dimensions.append(2)
            n /= 2
        f = 3
        while f * f <= n:
            if n % f == 0:
                dimensions.append(f)
                n /= f
            else:
                f += 2
        if n != 1: dimensions.append(int(n))
        # Only odd number is possible
        return dimensions

    def calculate_collage_size(self, images_dict: dict, margin_x = 0, margin_y = 0):

        collage_width = collage_height = 0

        for panel_id in images_dict.keys():
            image_rgb = images_dict[panel_id]
            image_width, image_height = image_rgb.size
            collage_width += image_width + Config.Default.Collage.margin_x
            collage_height += image_height + Config.Default.Collage.margin_y

        return collage_width, collage_height

    def draw_text_on_image(self, image_rgb, text, x = 3, y = 3, font_size = Config.Default.Font.size, font_path=Config.Default.Font.path):
        '''

        :param image_rgb: PIL.Image(RGB) object
        :param text: text you would like to draw
        :param x: x position of text
        :param y: y position of text
        :param font_size: size of the font
        :param font_path: path to TTF font
        :return: nothing (it draws on the original image passed as image_rgb)
        '''
        font = ImageFont.truetype(font_path, font_size)
        img_draw = ImageDraw.Draw(image_rgb)
        img_draw.text((x, y), text, font=font, fill=Config.Default.Font.fill)

    def number_to_prime_factors(number):
        x = number
        primes = list()
        p = 2
        while x > 2:
            while x % p == 0:
                x = x / p
                primes.append(p)
            p = p + 1
        return primes

    def dashboard_exists(self, dashboard_uid):
        '''

        :param dashboard_uuid:
        :return: boolean
        '''
        return self.api.dashboard_exists(dashboard_uid)

    def get_dashboard_title(self, dashboard_uid):
        return self.api.get_dashboard_title(dashboard_uid)

    def strip_datetime_to_minutes(self, datetime_string: str):
        return datetime_string.split(" ")[0]

    def get_dashboards(self):
        return self.api.get_dashboards_as_dict()

    def dir_exists(self, dir):
        return path.exists(dir)
