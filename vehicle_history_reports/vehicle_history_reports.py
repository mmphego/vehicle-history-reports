# -*- coding: utf-8 -*-

"""Main module."""

import json
import os
import re
import subprocess
import sys
import time
from base64 import b64encode

import psutil
from bs4 import BeautifulSoup

from loguru import logger
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class ProxySettings:
    """
    Proxy contains information about proxy type and necessary proxy settings.

    Attributes:
        host (str): host
        password (str): password
        port (str): port
        username (str): username
    """

    def __init__(self, **kwargs):
        self.host = kwargs.get("host", None)
        self.port = kwargs.get("port", None)
        self.username = kwargs.get("username", None)
        self.password = kwargs.get("password", None)

    def __repr__(self):
        return repr(
            "<{}(host='{}', port='{}', username='{}', password='{}') at 0x{:x}>".format(
                self.__class__.__name__,
                self.host,
                self.port,
                self.username,
                self.password,
                id(self),
            )
        )


class DataStructure:
    @staticmethod
    def asdict():
        return {
            "Additional Vehicle Info": {},
            "Decoded Details": {},
            "Images Links": {},
            "Most Recent Complaints": {},
            "Most Recent Recalls": {},
        }


class MissingPageSource(Exception):
    pass


class VehicleHistoryReports:
    def __init__(self, vin_number, log_level="INFO", timeout=60, **kwargs):
        """Summary

        Args:
            vin_number (str): VIN Number
            log_level (str, optional): Log Level
            timeout (int, optional): Web time-out
            **kwargs:
        """
        self._timeout = timeout
        self._closed = False
        self.data_structure = DataStructure.asdict()
        self.vin_number = vin_number
        # According to: https://en.wikipedia.org/wiki/Vehicle_identification_number
        assert len(self.vin_number) == 17, "ERROR: VIN Number should be 17 Characters."
        self.logger = logger
        self.logger.level(log_level.upper())
        self.proxy = None
        self._page_source = None
        if kwargs.get("host"):
            self.proxy = ProxySettings(**kwargs)

    def _setup_proxy(self):
        """Simplified Firefox Proxy settings"""
        firefox_profile = webdriver.FirefoxProfile()
        # Direct = 0, Manual = 1, PAC = 2, AUTODETECT = 4, SYSTEM = 5
        firefox_profile.set_preference("network.proxy.type", 1)
        firefox_profile.set_preference("signon.autologin.proxy", True)
        firefox_profile.set_preference("network.websocket.enabled", False)
        firefox_profile.set_preference("network.proxy.http", self.proxy.host)
        firefox_profile.set_preference("network.proxy.http_port", int(self.proxy.port))
        firefox_profile.set_preference("network.proxy.ssl", self.proxy.host)
        firefox_profile.set_preference("network.proxy.ssl_port", int(self.proxy.port))
        # firefox_profile.set_preference("network.automatic-ntlm-auth.allow-proxies", False)
        # firefox_profile.set_preference("network.negotiate-auth.allow-proxies", False)
        firefox_profile.set_preference(
            "network.proxy.no_proxies_on", "localhost, 127.0.0.1"
        )
        # Disable images for website to load quicker
        firefox_profile.set_preference("permissions.default.image", 2)
        # Disable Flash for website to load quicker
        firefox_profile.set_preference(
            "dom.ipc.plugins.enabled.libflashplayer.so", "false"
        )
        if self.proxy.username and self.proxy.password:
            firefox_profile.set_preference(
                "network.proxy.socks_username", self.proxy.username
            )
            firefox_profile.set_preference(
                "network.proxy.socks_password", self.proxy.password
            )
        # Deprecated
        # firefox_profile.add_extension('close_proxy_authentication-1.1.xpi')
        # credentials = f"{self.proxy.username}:{self.proxy.password}"
        # credentials = b64encode(credentials.encode("ascii")).decode("utf-8")
        # firefox_profile.set_preference("extensions.closeproxyauth.authtoken", credentials)
        firefox_profile.update_preferences()
        return firefox_profile

    def open_site(self, headless=False):
        """Simple selenium webdriver to open a known url"""
        options = Options()
        options.headless = headless
        profile = None
        if self.proxy:
            self.logger.info("Accessing URL using proxy settings: {}", self.proxy)
            profile = self._setup_proxy()

        self.driver = webdriver.Firefox(
            options=options, firefox_profile=profile, timeout=self._timeout
        )
        url = "https://driving-tests.org/vin-decoder/"
        self.logger.info("Accessing: {}", url)
        self.driver.get(url)
        self.logger.info("Successfully opened: {}", url)

    def navigate_site(self):
        """Navigate through the website"""
        form_id = "vin_input"
        # VIN inputform
        vin_input_form = WebDriverWait(self.driver, self._timeout).until(
            EC.presence_of_element_located((By.ID, form_id))
        )
        vin_input_form = self.driver.find_element_by_id(form_id)
        vin_input_form.send_keys(self.vin_number)
        # Press Enter key
        time.sleep(1)  # Wait a second before hitting the Enter
        self.logger.info("Searching for VIN: '{}' information.", self.vin_number)
        vin_input_form.send_keys(Keys.RETURN)
        retry = 0
        while True:
            # Wait until page is loaded!
            if (
                WebDriverWait(self.driver, self._timeout)
                .until(EC.presence_of_element_located((By.XPATH, '//*[@id="nhtsa-26"]')))
                .text
                != ""
            ):
                self.logger.info("Found VIN information, Scrapping data.")
                break
            retry += 1
            # wait arbitrary 5 seconds for page to load
            time.sleep(5)
            if retry >= 10:
                msg = f"Failed to retrieve VIN number information after {retry} retries."
                self.close_session()
                self.logger.error(msg)
                raise MissingPageSource(msg)
            self._no_vin_info()

    def _no_vin_info(self):
        """No data on website checker"""
        error_text = "we could not find information"
        if error_text in self.page_source.find(attrs={"class": "error-report"}).text:
            self.logger.error(self.page_source.find(attrs={"class": "error-report"}).text)
            self.close_session()

    @property
    def page_source(self):
        """Get page source as object"""
        self._page_source = BeautifulSoup(self.driver.page_source, "html.parser")
        return self._page_source

    def get_vehicle_details(self):
        """Get all vehicle details.

        Raises:
            MissingPageSource: If missing page source, raises error and closes browser
        """
        if not self.page_source:
            msg = f"Missing page source for vin:{self.vin_number}"
            self.logger.error(msg)
            self.close_session()
            raise MissingPageSource(msg)
        try:
            self.logger.info("Scrapping Decoded Details for vin: {}", self.vin_number)
            table_info = self._page_source.find(
                "table", attrs={"class": "tableinfo"}
            ).find("tbody")
            # Decoded Details
            for row in table_info.find_all("tr"):
                for key, value in zip(row.find_all("span"), row.find_all("td")):
                    self.data_structure["Decoded Details"][
                        "".join(value.text.split(key.text))
                    ] = "".join(key.text.split(value.text))
            table_striped = self._page_source.find(
                "table", attrs={"class": "table table-striped"}
            ).find("tbody")
            for row in table_striped.find_all("tr"):
                if len((row.text.strip().split("\n"))) == 2:
                    key, value = row.text.strip().split("\n")
                    self.data_structure["Decoded Details"][key] = value
            self.logger.info(
                "Updated data structure with table data for vehicle decoded details."
            )
            # Additional Vehicle Info
            self.logger.info(
                "Scrapping additional vehicle info for vin: {}", self.vin_number
            )
            additional_infos = self._page_source.find(attrs={"id": "report_extra"}).find(
                "tbody"
            )
            for row in additional_infos.find_all("tr"):
                self.data_structure["Additional Vehicle Info"][
                    "".join(row.td.text.split(row.text))
                ] = "".join(row.text.split(row.td.text))
            self.logger.info(
                "Updated data structure with table data for additional vehicle info."
            )
        except Exception as err:
            self.logger.exception("ERROR Occurred: {}", err)

    def _extract_table_info(self, recent_issues=None):
        """Convenience method for extracting tables from page source and
        update data structure

        Args:
            recent_issues (None, optional): This can either be recalls or complaints

        Raises:
            MissingPageSource: If missing page source, raises error and closes browser
        """
        if not self.page_source:
            msg = f"Missing page source for vin:{self.vin_number}"
            self.logger.error(msg)
            self.close_session()
            raise MissingPageSource(msg)

        if not recent_issues:
            recent_issues = "recalls"

        try:
            table = self._page_source.find(attrs={"id": f"{recent_issues.lower()}"})
            table_bodies = table.find_all("tbody")
        except Exception as err:
            self.logger.exception("ERROR Occurred: {}", err)
        else:
            self.logger.info("Scrapping table containing all {}", recent_issues)
            for count, tbody in enumerate(table_bodies, 1):
                rows = tbody.find_all("tr")
                self.data_structure[f"Most Recent {recent_issues.title()}"][
                    f"{recent_issues.lower()}_{count}"
                ] = {}
                for row in rows:
                    cols = row.find_all("td")
                    key, value = [
                        "".join(ele.text.strip("\n").split("\n")) for ele in cols
                    ]
                    self.data_structure[f"Most Recent {recent_issues.title()}"][
                        f"{recent_issues.lower()}_{count}"
                    ].update({key: value})
            self.logger.info(
                "Updated data structure with table data for {}", recent_issues
            )

    def get_recent_recalls(self):
        """Extract recent recalls"""
        return self._extract_table_info(recent_issues="recalls")

    def get_recent_complaints(self):
        """Extract recent complaints"""
        return self._extract_table_info(recent_issues="complaints")

    def get_image_links(self):
        """Extract image links and update data structure"""
        if not self.page_source:
            msg = f"Missing page source for vin:{self.vin_number}"
            self.logger.error(msg)
            raise MissingPageSource(msg)

        try:
            link = self.page_source.find("img", attrs={"id": "vehicle_logo"}).get(
                "src", None
            )
            vehicle_logo_url = "".join([self.driver.current_url, link]) if link else ""
            if vehicle_logo_url:
                self.logger.info("Found Vehicle Logo URL: {}", vehicle_logo_url)
            self.data_structure["Images Links"]["vehicle_logo"] = vehicle_logo_url
        except Exception as err:
            self.logger.exception("ERROR Occurred: {}", err)
        else:
            image_urls_class = self.page_source.find_all(
                "img", attrs={"class": "slick-slide"}
            )
            image_urls = [image_url.get("src", None) for image_url in image_urls_class]
            self.data_structure["Images Links"]["vehicle_images"] = image_urls
            if not image_urls:
                self.logger.info("Found NO Vehicle image links")
            self.logger.info("Updated data structure with vehicle and logo images.")

    @property
    def data_as_json(self):
        """Output in the form of json file"""
        return json.dumps(self.data_structure, sort_keys=True)

    def data_json_to_file(self, filename="data_structure.json"):
        """Save data structure as json file

        Args:
            filename (str, optional): Filename to save as.
        """
        self.logger.info("Writing data to json")
        with open(filename, "w") as json_file:
            json.dump(self.data_structure, json_file)

    def close_session(self):
        """Close browser and cleanup"""
        if not self._closed:
            self.logger.info("Closing the browser...")
            self.driver.close()
            self.driver.quit()
            time.sleep(1)

            PROCNAME = "geckodriver"
            self.logger.info("Cleaning up by killing {} process", PROCNAME)
            _ = [
                proc.terminate()
                for proc in psutil.process_iter()
                if proc.name() == PROCNAME
            ]
            self._closed = True
            self.logger.info("Done...")
