from CurrencyOption import CurrencyOption

import datetime
from multiprocessing import Process, Pipe, Manager
import numpy as np
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
import selenium.webdriver.support.ui as ui
from sys import exit
import time
import urllib


class NadexSearch:

    currencyPairs = ('AUD/JPY', 'AUD/USD', 'EUR/GBP', 'EUR/JPY', 'EUR/USD',
                     'GBP/JPY', 'GBP/USD', 'USD/CAD', 'USD/CHF', 'USD/JPY')

    iFrames = ('default', 'ifrMyPrices', 'ifrFinder', 'ifrDealingRates', 'ifrBetslip-0')
    currentFrame = iFrames[0]

    """                     FUNCTIONS                   """

    def __init__(self):
        self.driver = webdriver.Firefox()
        self.username = ""  # NOTE: Enter demo username here.
        self.password = ""  # NOTE: Enter demo password here.
        self.balance = -1
        self.purchaseInProgress = False
        self.optionList = []
        self.exchangeRates = {}

    def getExchangeRates(self):
        """Iterate over all currency pairs and save their exchange rates."""

        for pair in self.currencyPairs:
            self.exchangeRates[pair] = self.YahooExchangeRates(pair)
            # Try again if the page does not load correctly.
            while self.exchangeRates[pair] == 'Error.':
                self.exchangeRates[pair] = self.YahooExchangeRates(pair)

    def YahooExchangeRates(self, pair):
        """Uses regex to gather exchange rates for all currency pairs."""

        pair = pair.replace("/", "")
        url = 'http://finance.yahoo.com/q?s=' + pair + '=X'
        regex = '<span id="yfs_l10_' + pair.lower() + '=x">(.+?)</span>'
        pattern = re.compile(regex)
        htmltext = urllib.request.urlopen(url).read().decode("utf-8")
        results = re.findall(pattern, htmltext)

        try:
            exchangeRate = float(results[0])
        except IndexError:
            exchangeRate = "Error."

        return exchangeRate

    def signIn(self):
        """Goes to the Nadex website and signs in to a demo account."""

        self.driver.get("http://www.nadex.com/login.html")
        ui.WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "account_id")))

        # wait = ui.WebDriverWait(driver, 15)  # Times out after 15 seconds.

        elem = self.driver.find_element_by_id("account_id")
        elem.send_keys(self.username)
        elem = self.driver.find_element_by_id("password")
        elem.send_keys(self.password)
        elem.send_keys(Keys.RETURN)

        print("Waiting for page to load...")

        ui.WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.ID, "ifrMyPrices")))
        time.sleep(2)

        self.balance = self.getBalance()

        print("\rPage open.")
        time.sleep(1.2)
        print("\nWelcome. Your starting balance is: \t$" + str('%.2f' % self.balance))

        # For switching to custom watchlist.
        # driver.find_element_by_id("selectWatchlist_currVal").click()
        # driver.find_element_by_xpath('//*[@id="selectWatchlist_ddScroll"]/ul/li[16]').click()
        # time.sleep(10)

    def getBalance(self):
        """Returns the account's current balance as a floating point."""

        currentBalance = self.driver.execute_script("return parent.document.getElementById('rsrcBalance').textContent")
        currentBalance = currentBalance.replace('$', '')
        currentBalance = currentBalance.replace(',', '')
        currentBalance = float(currentBalance)
        return currentBalance

    def getOptionNames(self, clean=False):
        """Return a list of option names from the main Watchlist.
        Useful because the names of options are always changing.
        Clean=True will remove unpriced options."""

        names = self.driver.execute_script("""adrNames = window.parent.frames['ifrMyPrices'].document.getElementsByClassName('floatLeft tableIcon dealOpen');
                                              namesText = "";
                                              for(var i = 0; i < adrNames.length; i++){
                                                  namesText += adrNames[i].textContent + ",";
                                              }
                                              return namesText;""")

        nameList = [n for n in names.split(",")]

        del nameList[-1]

        if not nameList:
            print("There are no open contracts.")

        elif clean:
            priceList = self.getPrices(False)
            counter = 0
            while counter < len(priceList):
                if (len(priceList[counter]) < 4) or (len(priceList[counter + 1]) < 4):
                    del nameList[(counter//2)]
                counter += 2

        return nameList

    def getPrices(self, clean=False):
        """Returns a list of option prices from the main Watchlist.
        Useful for obvious reasons.
        Clean=True will remove unpriced options."""

        prices = self.driver.execute_script("""adrPrices = window.parent.frames['ifrMyPrices'].document.getElementsByClassName('price dealOpen');
                                               priceText = "";
                                               for(var j = 0; j < adrPrices.length; j++){
                                                   priceText += adrPrices[j].textContent + ",";
                                               }
                                               return priceText;""")

        priceList = [p for p in prices.split(",")]

        del priceList[-1]

        if not priceList:
            print("There are no open contracts.")

        else:
            for x in range(0, len(priceList)):
                try:
                    priceList[x] = float(priceList[x])
                except ValueError:
                    continue

            if clean:
                counter = 0
                while counter < len(priceList):
                    if not isinstance(priceList[counter], float):
                        del priceList[counter:counter+2]
                    else:
                        counter += 2

        return priceList

    def getExpireTimes(self):
        """Returns expire time in years.
        Why years? The interest rates are expressed in years, and the units must be consistent."""

        times = self.driver.execute_script("""adrTimes = window.parent.frames['ifrMyPrices'].document.getElementsByClassName('yui-dt0-col-timeToExpiry yui-dt-col-timeToExpiry yui-dt-sortable');
                                              timeText = "";
                                              for(var k = 0; k < adrTimes.length; k++){
                                              timeText += adrTimes[k].textContent + ",";
                                              }
                                              return timeText;""")
        timeList = [t.replace(" ", "") for t in times.split(',')]
        del timeList[0]  # Needed to remove title and empty string.
        del timeList[-1]

        for x in range(0, len(timeList)):
            if timeList[x] == '-':
                continue

            t = timeList[x]
            if any('h' == c for c in t):  # Not all timestamps are given in the same format.
                t = t.replace("h", "")
                t = t.replace("m", "")
                t = time.strptime(t, "%H:%M")
                t = datetime.timedelta(hours=t.tm_hour, minutes=t.tm_min).total_seconds()

            elif any('m' == c for c in t):
                t = t.replace("m", "")
                t = t.replace("s", "")

                try:
                    t = time.strptime(t, "%M:%S")
                    t = datetime.timedelta(minutes=t.tm_min, seconds=t.tm_sec).total_seconds()
                except:  # FIX ME: catch actual exception
                    t = "0"+t
                    t = time.strptime(t, "%M:%S")
                    t = datetime.timedelta(minutes=t.tm_min, seconds=t.tm_sec).total_seconds()

            else:
                t = t.replace("s", "")
                t = time.strptime(t, "%S")
                t = datetime.timedelta(seconds=t.tm_sec).total_seconds()

            t /= 31536000.0
            timeList[x] = t

        return timeList

    def getIndicatives(self):
        """Returns the underlying indicative values."""

        indicatives = self.driver.execute_script("""adrUnd = window.parent.frames['ifrMyPrices'].document.getElementsByClassName('yui-dt0-col-underlyingIndicativePrice yui-dt-col-underlyingIndicativePrice');
                                            undText = "";
                                            for(var l = 1; l < adrUnd.length; l++){
                                                undText += adrUnd[l].textContent + ",";
                                            }
                                            return undText;""")
        indicativesList = [float(i) if ('.' in i) else i for i in indicatives.split(',')]
        return indicativesList

    def makeOptions(self, childPipes):
        """Not really sure what this does.
        Makes instances of my option class for each open contract?"""

        names = self.getOptionNames(False)
        if not names:
            return None
        expiry = self.getExpireTimes()
        underlying = self.getIndicatives()
        prices = self.getPrices(False)

        for x, name in enumerate(names):
            currentPair = name.split(" ")[0]
            if not any(currentPair == pair for pair in self.currencyPairs):
                continue
            if prices[2*x] == '-' or prices[2*x+1] == '-':
                continue

            newOption = CurrencyOption(name,
									   prices[2*x],
									   prices[2*x + 1],
									   self.exchangeRates[currentPair],
									   expiry[x],
									   underlying[x],
									   childPipes[x],
									   motherOfAllBuyPrices[x],
									   motherOfAllSellPrices[x],
									   motherOfAllUnderlying[x])
            self.optionList.append(newOption)

    def scanner(self, spread):
        """Displays options with specified spread. Useful for making trades manually."""

        names = self.getOptionNames(False)
        if not names:
            return

        prices = self.getPrices(True)
        if not prices:
            print("There are no priced contracts.")
            return

        print("Name", '%44s' % "Sell", "   Buy       Spread\n")
        n = 0
        p = 0
        frmt = "%*s%*s%*s%*s"

        while n < len(names):
            try:  # try is necessary to prevent errors from '-' prices.
                differential = abs(float(prices[p]) - float(prices[p+1]))
                if differential <= spread:
                    print(frmt % (0, names[n], 50-len(names[n]), prices[p], 7, prices[p+1], 9, differential))
            except TypeError:
                pass

            n += 1
            p += 2

    def priceHistory(self, length, optionConnections, timeConnection, gatheringConnection):
        """This function has not been tested yet!
        I believe this was supposed to be run in a separate process and simply collect price data.
        Probably not useful for arbitrage."""

        global processIDs
        proxyList = processIDs
        proxyList.append(os.getpid())
        processIDs = proxyList

        buyList = []
        sellList = []
        times = []

        currentPrices = self.getPrices(False)

        for x in range(0, len(currentPrices)//2):
            buyList.append([currentPrices[2*x + 1]])
            sellList.append([currentPrices[2*x]])

        gatheringConnection.send(True)
        counter = 0

        while True:
            start_time = time.time()
            print("Start")

            if len(currentPrices) != length:
                gatheringConnection.send(False)
                print("The amount of open contracts has changed.")
                exit()

            else:
                currentTimes = self.getExpireTimes()
                currentUnderlying = self.getIndicatives()
                currentPrices = self.getPrices(False)

                for p in range(0, len(currentPrices)//2):
                    buyList[p].append(currentPrices[p*2 + 1])
                    sellList[p].append(currentPrices[p*2])
                    print(sellList[p], buyList[p], currentTimes[p], currentUnderlying[p])
                    optionConnections[p].send((sellList[p], buyList[p], currentTimes[p], currentUnderlying[p]))

                times.append(time.time() - start_time)

                timeConnection.send(times)

                print("End ", counter)
                counter += 1

    def startTrading(self, childPipes):
        """Launches processes for each option."""

        if not self.optionList:
            self.makeOptions(childPipes)

        for option in self.optionList:
            Process(target=self.analyzeData, args=(option,)).start()
            time.sleep(1)

        print("Analysis has begun.")

    def analyzeData(self, option):
        """This is a place for *very* basic trading algorithms for testing, not for winning.
        Currently does nothing interesting. Make it trade off of the Greeks or something."""

        # global processIDs
        # proxyList = processIDs
        # currentProcess = os.getpid()
        # proxyList.append(currentProcess)
        # processIDs = proxyList

        while True:
            if abs(option.buyPrice - option.sellPrice) <= 5:
                if option.strike/option.underlying <= 0.9 and option.delta() <= 0.5:
                    option.buy(lotSize=1, short=True)
                    exit()
                elif 1 >= option.strike/option.underlying >= 0.995 and option.delta() > 0:
                    option.buy(lotSize=1, short=False)
                    exit()
                elif 1 >= option.strike/option.underlying >= 0.995 and option.delta() < 0:
                    option.buy(lotSize=1, short=True)
                    exit()
                elif 1.01 >= option.strike/option.underlying >= 1 and option.delta() < 0:
                    option.buy(lotSize=1, short=True)
                    exit()

    def placeOrderExample(self):
        """Places an order with no strategy, just to demonstrate that it works."""

        if not self.optionList:
            return "There are no contracts to order."

        for option in self.optionList:
            start_time = time.time()
            option.buy(lotSize=1, short=False)
            timeTracker[9].append(time.time() - start_time)
            print("Average time: ", np.mean(timeTracker[9]))

    def buy(self, option, lotSize=1, short=False):
        """Buys the option."""

        global ticketsOpen

        while self.purchaseInProgress:
            pass
        self.purchaseInProgress = True

        try:
            self.driver.find_element_by_link_text(option.name).click()
            ticketsOpen += 1
            ticket = str(ticketsOpen)
        except:  # FIX ME: catch actual exception
            return "Link_text not found."

        # This is here to prevent the code from executing before the order form has even opened.
        loaded = False
        while not loaded:
            try:
                float(self.driver.execute_script("return window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('dmaPriceCurrent').textContent"))
                loaded = True
            except:  # FIX ME: catch actual exception
                pass

        # This chunk actually places the order.
        # The above chunk of code doesn't slow the execution enough.
        # Unfortunately I cannot come up with a better way of further slowing it down enough other than time.sleep().
        time.sleep(0.45)
        try:
            self.driver.execute_script("window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('directionChange').click()")  # Once for buy, twice for sell.
            self.driver.execute_script("window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('size').value = "+str(lotSize))
            if short:
                self.driver.execute_script("window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('directionChange').click()")
                self.driver.execute_script("window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('level').value = "+str(option.sellPrice))
            else:
                self.driver.execute_script("window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('level').value = "+str(option.buyPrice))
            self.driver.execute_script("window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('btnSubmit').click()")
            loaded = False
        except:  # FIX ME: catch actual exception
            print("Error filling buyslip.")

        while not loaded:
            try:
                self.driver.execute_script("window.parent.frames['ifrBetslip-"+ticket+"'].document.getElementById('betslipBtnClose').click()")
                loaded = True
            except:  # FIX ME: catch actual exception
                pass

        ticketsOpen -= 1
        self.purchaseInProgress = False

    def fillWatchlist(self):
        """Code looks awful, I'll have to overhaul it when it comes time I finally need it.
        Used for creating a custom watchlist, filled with every Forex binary option.
        This is useful because Nadex does not save the entire watchlist, and thus it needs to be updated from time to time."""

        self.driver.switch_to_default_content()
        self.driver.switch_to_frame("ifrFinder")
        self.currentFrame = 'ifrFinder'
        ui.WebSelf.DriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "ygtvt4")))
        self.driver.find_element_by_id("ygtvt4").click()
        ui.WebSelf.DriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "ygtvt8")))

        for number in range(8, 17):
            ID = "ygtvt" + str(number)
            self.driver.find_element_by_id(ID).click()

        for number in range(18, 87):

            ID = "ygtvlabelel" + str(number)
            self.driver.find_element_by_id(ID).click()
            self.driver.switch_to_default_content()
            self.driver.switch_to_frame("ifrDealingRates")
            time.sleep(3)

            buttons = self.driver.find_elements_by_css_selector(".optionsBtn")

            for button in buttons:

                button.click()
                self.driver.switch_to_default_content()
                ui.WebSelf.DriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "PORTFOLIO")))
                self.driver.find_element_by_xpath('//*[@id="PORTFOLIO"]/a').click()
                self.driver.switch_to_frame("ifrDealingRates")

            self.driver.switch_to_default_content()
            self.driver.switch_to_frame("ifrFinder")

    def JStest(self):
        """Starts running a JavaScript 'console' for debugging purposes."""

        print('Type "exit JS" to quit.')
        command = input('>>>')

        while command != 'exit JS':
            try:
                self.driver.execute_script(command)
                try:
                    print(self.driver.execute_script(command))
                except:  # FIX ME: catch actual exception
                    pass
            except:  # FIX ME: catch actual exception
                print("Error")

            command = input('>>>')

    def mainMenu(self):
        """The main menu of the program where the user can manually tell it what to do.
        Mostly for debuging purposes, since most of these things should be automated eventually."""

        global optionConnectionParent, optionConnectionChild, priceGatheringChild, priceGatheringParent
        global motherOfAllUnderlying, currentExpiries
        global price_time_parent, price_time_child

        priceGatheringChild.send(False)

        while True:
            print("\nPress 1 to scan for options.\nPress 2 to fill the watchlist with open Forex binaries.")
            print("Press 3 to demonstrate purchasing.\nPress 4 to print option names.\nPress 5 to print option prices.")
            print("Press 6 to start gathering price data.\nPress 7 to print sell price data.\nPress 8 to print buy price data.")
            menu = str(input("Press 9 to start trading.\nPress 0 to enter JavaScript console.")).lower()

            if menu == "1":
                spread = eval(input("Enter a spread: "))
                start_time = time.time()

                self.scanner(spread)

                timeTracker[1].append(time.time() - start_time)
                print("\nTime elapsed: ", timeTracker[1][-1], "seconds.")
                print("Average time: ", np.mean(timeTracker[1]), "seconds.")

            elif menu == "2":
                start_time = time.time()
                self.fillWatchlist()
                timeTracker[2].append(time.time() - start_time)
                print("\nTime elapsed: ", timeTracker[2][-1], "seconds.")
                print("Average time: ", np.mean(timeTracker[2]), "seconds.")

            elif menu == "3":
                if not priceGatheringParent.recv():
                    currentPrices = self.getPrices()
                    if currentPrices:

                        for x in range(0, len(currentPrices)):
                            newParent, newChild = Pipe()
                            optionConnectionParent.append(newParent)
                            optionConnectionChild.append(newChild)

                        priceHistoryProcess = Process(target=self.priceHistory,
                                                      args=(len(currentPrices),
                                                            optionConnectionChild,
                                                            price_time_child,
                                                            priceGatheringChild))
                        priceHistoryProcess.start()

                if not self.optionList:
                    self.makeOptions(optionConnectionChild)

                purchasingDemonstration = Process(target=self.placeOrderExample, args=())
                purchasingDemonstration.start()
                purchasingDemonstration.join()

            elif menu == "4":
                clean = input("Remove unpriced options? [0/1]")

                if clean == '0':
                    clean = False
                elif clean == '1':
                    clean = True
                else:
                    print("Invalid input, assuming 1.")
                    clean = True

                try:
                    start_time = time.time()

                    print(self.getOptionNames(clean))

                    timeTracker[4].append(time.time() - start_time)
                    print("\nTime elapsed: ", timeTracker[4][-1], "seconds.")
                    print("Average time: ", np.mean(timeTracker[4]), "seconds.")

                except:  # FIX ME: catch actual exception
                    print("Invalid input")

            elif menu == "5":
                clean = input("Remove unpriced options? [0/1]")

                if clean == '0':
                    clean = False
                elif clean == '1':
                    clean = True
                else:
                    print("Invalid input, assuming 1.")

                try:
                    start_time = time.time()

                    print(self.getPrices(clean))
                    timeTracker[5].append(time.time() - start_time)
                    print("\nTime elapsed: ", timeTracker[5][-1], "seconds.")
                    print("Average time: ", np.mean(timeTracker[5]), "seconds.")

                except:  # FIX ME: catch actual exception
                    print("Invalid input")

            elif menu == "6":
                if not priceGatheringParent.recv():
                    currentPrices = self.getPrices()
                    if currentPrices:
                        # optionConnectionParent, optionConnectionChild = [Pipe() for p in currentPrices]
                        for x in range(0, len(currentPrices)):
                            newParent, newChild = Pipe()
                            optionConnectionParent.append(newParent)
                            optionConnectionChild.append(newChild)

                        priceHistoryProcess = Process(target=self.priceHistory, args=(len(currentPrices), optionConnectionChild, price_time_child, priceGatheringChild))
                        priceHistoryProcess.start()
                else:
                    print("This process is already running.")

            elif menu == "7":
                for pipe in optionConnectionParent:
                    print(pipe.recv())

            elif menu == "8":
                for pipe in optionConnectionParent:
                    print(pipe.recv())

            elif menu == "9":
                if not priceGatheringParent.recv():
                    currentPrices = self.getPrices()
                    if currentPrices:
                        # optionConnectionParent, optionConnectionChild = [Pipe() for p in currentPrices]
                        for x in range(0, len(currentPrices)):
                            newParent, newChild = Pipe()
                            optionConnectionParent.append(newParent)
                            optionConnectionChild.append(newChild)

                        priceHistoryProcess = Process(target=self.priceHistory,
                                                      args=(len(currentPrices),
                                                            optionConnectionChild,
                                                            price_time_child,
                                                            priceGatheringChild))
                        priceHistoryProcess.start()
                        while not motherOfAllSellPrices:
                            pass

                self.startTrading(optionConnectionChild)

            elif menu == "0":
                self.JStest()

            elif menu.lower() in ("exit", "quit", "stop", "abort", "end"):
                break

            else:
                print("Invalid input.")


"""                     GLOBAL VARIABLES            """
manager = Manager()
motherOfAllBuyPrices = manager.list()
motherOfAllContractNames = manager.list()
motherOfAllSellPrices = manager.list()
motherOfAllUnderlying = manager.list()
currentExpiries = manager.list()
nadex = NadexSearch()
processIDs = manager.list()
queueList = []

# EUR rate is incorrect. I don't know how to find the risk-free rate for the EU as a whole.
# I'm making the approximation that it's equal to the UK's.
ticketsOpen = -1
timeTracker = [[] for i in range(1, 11)]

"""                     PIPES                       """

optionConnectionParent = []
optionConnectionChild = []  # Later these are turned into arrays of pipes
priceGatheringParent, priceGatheringChild = Pipe()
price_time_parent, price_time_child = Pipe()

"""                     MAIN                        """

# Gather exchange rates headlessly while the browser signs in.
rates = Process(target=nadex.getExchangeRates, args=())
rates.start()

nadex.signIn()

rates.join()

nadex.mainMenu()

print("\nFinished.")

"""
                            THINGS TO CLEAN UP:

-Remove all globals and make them attributes of the class.
-Make all exceptions specify a type of exeption.
-Look for an remove redundant/useless code.

"""

"""
                            KNOWN BUGS:

# priceHistory() is broken: doesn't return times or underlying; prices stop being appended to the list after a short while.

                            TO DO:

# Remove global variables and place them inside the class.

# Create a "process manager" class to control the processes.

#

# Arbitrage!

# A function is needed to monitor working orders.

# A function is needed to monitor open positions.

"""