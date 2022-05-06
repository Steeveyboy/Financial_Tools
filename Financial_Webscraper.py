import time
from selenium import webdriver
Path = r"C:\Users\jonat\Downloads\chromedriver.exe"

browser = webdriver.Chrome(Path)

browser.get("https://www.python.org/")

time.sleep(3)

browser.quit()


