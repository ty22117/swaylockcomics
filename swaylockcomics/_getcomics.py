#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pendulum
import requests
from bs4 import BeautifulSoup as bs
from PIL import Image, ImageFont, ImageDraw
import json
import re
import os
import glob
import sys

now = pendulum.now().format("YYYY-MM-DD")
comic_names = []

# The font directory is one level higher than this file.
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def get_font(fontname, size):
    try:
        font_object = ImageFont.truetype(os.path.join(FONT_DIR, fontname), size)
        return font_object
    except OSError:
        print("Couldn't find font '{}'".format(fontname))
        print("Searched {}".format(FONT_DIR))
        sys.exit()


def text_wrap(text, font, max_width, margin):
    max_width -= margin * 2
    lines = []
    # If the width of the text is smaller than image width
    # we don't need to split it, just add it to the lines array
    # and return
    if font.getsize(text)[0] <= max_width:
        lines.append(text)
    else:
        # split the line by spaces to get words
        words = text.split(" ")
        i = 0
        # append every word to a line while its width is shorter than
        # image width
        while i < len(words):
            line = ""
            while i < len(words) and font.getsize(line + words[i])[0] <= max_width:
                line = line + words[i] + " "
                i += 1
            if not line:
                line = words[i]
                i += 1
            # when the line gets longer than the max width do not
            # append the word, add the line to the lines array
            lines.append(line)
    return lines


def draw_text(text, image, font, margin):
    # open the background file
    img = Image.open(image)

    # size() returns a tuple of (width, height)
    image_size = img.size

    # get shorter lines
    lines = text_wrap(text, font, image_size[0], margin)
    return lines


def get_backup_strip(comic, cachedir, sysdir):
    """
    1. Use earlier strip of same comic as chosen if available
    2. Use fallback xkcd strip
    """
    strips_files = glob.glob("{}/strips/*{}*".format(cachedir, comic))
    if strips_files:
        backup_strip = sorted(strips_files)[-1]
    else:
        backup_strip = "{}/temp/xkcd.png".format(cachedir)
    return backup_strip


def xkcd_alttext(comic_in, extra_info):
    _comic = Image.open(comic_in)
    canvas_width = _comic.size[0]
    canvas_height = _comic.size[1]
    text_font = get_font("OpenSans-Italic.ttf", 18)
    margin = 10
    text_split = draw_text(extra_info, comic_in, text_font, margin)
    new_canvas_height = canvas_height + (22 * len(text_split)) + 22
    img = Image.new("RGB", (canvas_width, new_canvas_height), "white")
    img.paste(_comic, (0, 0))
    out = ImageDraw.Draw(img)
    i = 0
    ver = canvas_height + 10
    for line in text_split:
        out.text((margin, ver + i), line, font=text_font, fill=(0, 0, 0))
        i += 22
    img.save(comic_in)
    return comic_in


def comics(comic=False):
    def get_gocomics(url, expected_date=None):
        """
        Get comic image from gocomics.com.
        The site was redesigned and no longer uses the gc-deck--cta-0 class.
        The comic image URL is now embedded in an application/ld+json
        ImageObject script tag containing the comic date.

        Args:
            url: The URL to fetch the comic from
            expected_date: Optional pendulum date object to match against comic name
        """
        import json as _json

        if expected_date:
            date_to_match = expected_date.format("MMMM D, YYYY")
        else:
            date_to_match = pendulum.now().format("MMMM D, YYYY")

        req = requests.get(
            url,
            timeout=5,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"
                " AppleWebKit/537.36 Chrome/120 Safari/537.36"
            },
        )
        scripts = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            req.text,
            re.DOTALL,
        )
        for s in scripts:
            try:
                d = _json.loads(s)
                if d.get("@type") == "ImageObject" and date_to_match in d.get(
                    "name", ""
                ):
                    link = d.get("contentUrl", "")
                    if link:
                        return link
            except Exception:
                continue
        raise ValueError("Could not find comic image for {}".format(url))

    def getcomic_xkcd():
        """
        Gets the link to the most recent xkcd comic strip.
        """
        try:
            current_strip = requests.get("https://xkcd.com/info.0.json", timeout=3)
            current_json = json.loads(current_strip.text)
            link = current_json["img"]
            extra_info = '"{}"'.format(current_json["alt"])
        except:
            link = False
            extra_info = ""
        return {"link": link, "extra_info": extra_info}

    def getcomic_lunch():
        """
        Gets the link to the most recent Lunch comic strip.
        """
        try:
            req = requests.get("https://www.tu.no/tegneserier/lunch", timeout=3)
            soup = bs(req.content, "html5lib", from_encoding="utf-8")
            figure = soup.find("section", attrs={"class": "feed-comics"}).find_all(
                "figure"
            )[-1]
            link = "https://www.tu.no"
            link += figure.find("div", attrs={"class": "image-container"}).find("img")[
                "src"
            ]
        except:
            link = False
        return {"link": link}

    def getcomic_dilbert():
        """
        Gets the link to the most recent Dilbert comic strip.
        """
        global now
        try:
            req = requests.get("http://dilbert.com/strip/{}".format(now), timeout=3)
            soup = bs(req.content, "html5lib", from_encoding="utf-8")
            strip = soup.find("div", attrs={"class": "img-comic-container"})
            link = strip.find("img", attrs={"class": "img-responsive img-comic"})["src"]
        except:
            link = False
        return {"link": link}

    def getcomic_commitstrip():
        """
        Gets the link to the most recent CommitStrip comic strip.
        """
        #        try:
        req = requests.get("http://www.commitstrip.com/en/feed/", timeout=3)
        soup = bs(req.content, "html5lib", from_encoding="utf-8").find_all("item")[0]
        link = soup.find("content:encoded").find("img")["src"]
        return {"link": link}

    def getcomic_pvp():
        """
        Gets the link to the most recent PvP comic strip.
        """
        try:
            req = requests.get("http://pvponline.com/comic", timeout=3)
            soup = bs(req.content, "html5lib", from_encoding="utf-8")
            link = soup.find("section", attrs={"class": "comic-art"}).find("img")["src"]
        except:
            link = False
        return {"link": link}

    def getcomic_dinosaurcomics():
        """
        Gets the link to the most recent Dinosaur Comics comic strip.
        """
        try:
            req = requests.get("http://www.qwantz.com/rssfeed.php", timeout=3)
            soup = bs(req.content, "html5lib", from_encoding="iso-5589-1")
            imgs = soup.find_all("item")
            link = re.search(r"img src=\"(.*\.png)", str(imgs[0])).group(1)
        except:
            link = False
        return {"link": link}

    def getcomic_getfuzzy():
        """
        Gets the link to the most recent Get Fuzzy comic strip.
        """
        try:
            dated = pendulum.now().format("YYYY/MM/DD")
            link = get_gocomics("https://www.gocomics.com/getfuzzy/{}".format(dated))
        except:
            link = False
        return {"link": link}

    def getcomic_calvinandhobbes():
        """
        Gets a random Calvin and Hobbes comic strip.
        Calvin and Hobbes ran from November 18, 1985 to December 31, 1995.
        """
        import random

        try:
            # Calvin and Hobbes date range
            start_date = pendulum.parse("1985-11-18")
            end_date = pendulum.parse("1995-12-31")
            # Generate random date within the range
            days_between = (end_date - start_date).days
            random_days = random.randint(0, days_between)
            random_date = start_date.add(days=random_days)
            dated = random_date.format("YYYY/MM/DD")
            link = get_gocomics(
                "https://www.gocomics.com/calvinandhobbes/{}".format(dated),
                expected_date=random_date,
            )
            comic_date = random_date.format("YYYY-MM-DD")
        except Exception as e:
            print(f"Error fetching Calvin and Hobbes: {e}")
            import traceback

            traceback.print_exc()
            link = False
            comic_date = None
        return {"link": link, "comic_date": comic_date}

    if comic == "xkcd":
        link = getcomic_xkcd()["link"]
        extra_info = getcomic_xkcd()["extra_info"]
        return {"link": link, "extra_info": extra_info}
    elif comic:
        result = eval("getcomic_{}()".format(comic))
        # Always include link and extra_info, add any other keys from result
        return_dict = {
            "link": result.get("link", False),
            "extra_info": result.get("extra_info", ""),
        }
        # Include any additional keys (like comic_date for calvinandhobbes)
        for key in result:
            if key not in ["link", "extra_info"]:
                return_dict[key] = result[key]
        return return_dict
    else:
        # Get all the available functions that is comic-related
        comic_names = []
        for func in dir():
            if "getcomic_" in func:
                func = func.replace("getcomic_", "")
                comic_names.append(func)
        return comic_names


def print_comic_list():
    """Print a list of available comics"""
    _comics = comics()
    out = "Comics found: "
    for comic in _comics:
        if comic == _comics[-1]:
            out += "and '{}'".format(comic)
        else:
            out += "'{}', ".format(comic)
    print(out)


if __name__ == "__main__":
    print_comic_list()
