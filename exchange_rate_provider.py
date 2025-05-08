import requests
import logging
import logging.handlers
import os

class ExchangeRateProvider:
    def __init__(self, api_key, base_currency='USD', target_currency='ARS', log_file_dir='log', log_file_name='exchange_rate.log'):
        self.api_key = api_key
        self.base_currency = base_currency
        self.target_currency = target_currency
        self.api_url = f"https://v6.exchangerate-api.com/v6/{self.api_key}/latest/{self.base_currency}"
        self.last_known_rate = None

        # Ensure log directory exists
        if not os.path.exists(log_file_dir):
            try:
                os.makedirs(log_file_dir)
            except OSError as e:
                print(f"Error creating log directory {log_file_dir}: {e}") 
                # Fallback to current directory if creation fails
                log_file_dir = '.'


        log_file_path = os.path.join(log_file_dir, log_file_name)

        # Setup logger for this class
        self.logger = logging.getLogger(__name__) # Use __name__ for module-specific logger
        if not self.logger.handlers: # Avoid adding multiple handlers if class is instantiated multiple times
            self.logger.setLevel(logging.INFO)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            
            # Rotating File Handler (by size)
            # Max 50MB per file, 1 backup file.
            rfh = logging.handlers.RotatingFileHandler(
                log_file_path, 
                maxBytes=50*1024*1024, # 50 MB
                backupCount=1,
                encoding='utf-8'
            )
            rfh.setFormatter(formatter)
            self.logger.addHandler(rfh)

            # Optional: Console handler for this logger for easier debugging
            # ch = logging.StreamHandler()
            # ch.setFormatter(formatter)
            # self.logger.addHandler(ch)
            
        self.logger.info(f"ExchangeRateProvider initialized for {base_currency} to {target_currency}.")

    def get_conversion_rate(self):
        """
        Fetches the conversion rate from the base currency to the target currency.
        Returns the rate if successful, otherwise returns the last known rate.
        If no rate has ever been successfully fetched, returns None.
        """
        self.logger.info(f"Attempting to fetch conversion rate for {self.base_currency} to {self.target_currency} from API.")
        try:
            response = requests.get(self.api_url, timeout=10) # Added timeout
            response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
            
            data = response.json()

            if data.get('result') == 'success':
                rates = data.get('conversion_rates')
                if rates and self.target_currency in rates:
                    rate = rates[self.target_currency]
                    self.last_known_rate = float(rate)
                    self.logger.info(f"Successfully fetched and updated rate for {self.base_currency} to {self.target_currency}: {self.last_known_rate}")
                    return self.last_known_rate
                else:
                    self.logger.error(f"Target currency '{self.target_currency}' not found in API response rates. Response: {data}")
            else:
                self.logger.error(f"API call did not report success. Result: {data.get('result')}. Error type: {data.get('error-type')}")

        except requests.exceptions.Timeout:
            self.logger.error(f"Request timed out while fetching exchange rate from {self.api_url}")
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP error occurred: {e} while fetching from {self.api_url}")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error occurred: {e} while fetching from {self.api_url}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"An ambiguous request error occurred: {e} while fetching from {self.api_url}")
        except ValueError as e: # Includes JSONDecodeError
            self.logger.error(f"Failed to decode JSON response or convert rate to float: {e}")
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}", exc_info=True)

        if self.last_known_rate is not None:
            self.logger.warning(f"API fetch failed. Returning last known rate: {self.last_known_rate}")
            return self.last_known_rate
        else:
            self.logger.error("API fetch failed and no previous rate is known.")
            return None

if __name__ == '__main__':
    # Example Usage (for testing this module directly)
    # You'll need to replace 'YOUR_API_KEY_HERE' with your actual key.
    # And ensure the 'log' directory exists or the fallback works.
    
    print("Testing ExchangeRateProvider...")
    # Create log directory for test if it doesn't exist
    if not os.path.exists('log'):
        os.makedirs('log')
        
    api_key_for_test = os.environ.get('EXCHANGERATE_API_KEY') # Try to get from env var
    if not api_key_for_test:
        api_key_for_test = input("Please enter your ExchangeRate-API key for testing: ")

    if api_key_for_test and api_key_for_test != 'YOUR_API_KEY_HERE':
        provider = ExchangeRateProvider(api_key=api_key_for_test)
        
        print(f"Fetching {provider.base_currency} to {provider.target_currency} rate...")
        rate = provider.get_conversion_rate()
        if rate is not None:
            print(f"Current {provider.base_currency} to {provider.target_currency} rate: {rate}")
            # Test with an amount
            amount_usd = 100
            amount_ars = amount_usd * rate
            print(f"{amount_usd} {provider.base_currency} is approximately {amount_ars:.2f} {provider.target_currency}")
        else:
            print(f"Failed to retrieve {provider.base_currency} to {provider.target_currency} rate.")

        print("\nSecond call (should use cached/newly fetched if API fails/succeeds):")
        rate2 = provider.get_conversion_rate()
        if rate2 is not None:
            print(f"Current {provider.base_currency} to {provider.target_currency} rate (call 2): {rate2}")
        else:
            print(f"Failed to retrieve {provider.base_currency} to {provider.target_currency} rate (call 2).")
            
        # Test error case by providing a wrong key (example)
        print("\nTesting with a deliberately wrong API key (expecting failure):")
        wrong_key_provider = ExchangeRateProvider(api_key='WRONG_API_KEY_TEST')
        wrong_rate = wrong_key_provider.get_conversion_rate()
        if wrong_rate is None:
            print("Correctly failed to retrieve rate with wrong API key.")
        else:
            print(f"Unexpectedly got a rate with wrong API key: {wrong_rate}")

    else:
        print("API key not provided or is the placeholder. Skipping live test.")
    
    print("\nTest finished. Check 'log/exchange_rate.log' for logs.") 