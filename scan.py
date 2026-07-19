import os
import requests
import logging
import time
from mnemonic import Mnemonic
from web3 import Web3
from bip32utils import BIP32Key
import hashlib
try:
    import bitcoinlib
except ImportError:
    print("Please install bitcoinlib: pip install bitcoinlib")
    exit(1)
try:
    from solana.rpc.api import Client as SolanaClient
    from solana.keypair import Keypair
except ImportError:
    SolanaClient = None

from tqdm import tqdm  # For progress bar

# Configuration
ALCHEMY_API_KEY = 'YOUR_ALCHEMY_API_KEY'  # <-- Replace with your actual API key
ETH_ALCHEMY_URL = f'https://eth-mainnet.alchemyapi.io/v2/{ALCHEMY_API_KEY}'
BTC_API_URL = 'https://blockchain.info/balance?active='
SOLANA_RPC_URL = 'https://api.mainnet.solana.com'

MNEMONICS_FILE = 'mnemonics_list.txt'
LOG_FILE = 'bal.txt'
ERROR_LOG_FILE = 'errors.log'

# Derivation paths for each network
DERIVATION_PATHS = {
    'ethereum': "m/44'/60'/0'/0/0",
    'bitcoin': "m/44'/0'/0'/0/0",
    'solana': "m/44'/501'/0'/0/0"
}

# ERC20 tokens configuration
ERC20_TOKENS = [
    {
        'name': 'USDT',
        'address': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
        'decimals': 6
    },
    {
        'name': 'USDC',
        'address': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
        'decimals': 6
    },
    {
        'name': 'DAI',
        'address': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
        'decimals': 18
    },
    {
        'name': 'LINK',
        'address': '0x514910771AF9Ca656af840dff83E8264EcF986CA',
        'decimals': 18
    },
    {
        'name': 'UNI',
        'address': '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
        'decimals': 18
    },
    {
        'name': 'MKR',
        'address': '0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2',
        'decimals': 18
    },
    {
        'name': 'COMP',
        'address': '0xc00e94Cb662C3520282E6f5717214004A7f26888',
        'decimals': 18
    },
    {
        'name': 'AAVE',
        'address': '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9',
        'decimals': 18
    },
    {
        'name': 'SNX',
        'address': '0xF129567dB0d22f160235f06ab1737C4087363b1f',
        'decimals': 18
    },
    {
        'name': 'YFI',
        'address': '0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e',
        'decimals': 18
    }
]

# Setup logging
logging.basicConfig(filename=ERROR_LOG_FILE, level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Web3
web3 = Web3(Web3.HTTPProvider(ETH_ALCHEMY_URL))
if not web3.isConnected():
    print("Error: Cannot connect to Ethereum node. Check your API key.")
    exit(1)

# Initialize Solana client if available
solana_client = None
if SolanaClient:
    solana_client = SolanaClient(SOLANA_RPC_URL)

# Load mnemonics
try:
    with open(MNEMONICS_FILE, 'r') as f:
        mnemonics = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    print(f"Error: {MNEMONICS_FILE} not found.")
    exit(1)

# Helper functions

def derive_eth_address(seed_bytes):
    try:
        master_key = BIP32Key.fromEntropy(seed_bytes)
        path = DERIVATION_PATHS['ethereum']
        segments = path.replace('m/', '').split('/')
        key = master_key
        for segment in segments:
            hardened = segment.endswith("'")
            index = int(segment[:-1]) if hardened else int(segment)
            key = key.ChildKey(index + (0x80000000 if hardened else 0))
        pubkey = key.PublicKey()
        address_bytes = Web3.keccak(pubkey)[-20:]
        address = Web3.toChecksumAddress(address_bytes)
        return address
    except Exception as e:
        logging.error(f"ETH address derivation error: {e}")
        return None

def derive_btc_address(seed_bytes):
    try:
        master_key = BIP32Key.fromEntropy(seed_bytes)
        path = DERIVATION_PATHS['bitcoin']
        segments = path.replace('m/', '').split('/')
        key = master_key
        for segment in segments:
            hardened = segment.endswith("'")
            index = int(segment[:-1]) if hardened else int(segment)
            key = key.ChildKey(index + (0x80000000 if hardened else 0))
        pubkey = key.PublicKey()
        # Using bitcoinlib for address encoding
        btc_address_obj = bitcoinlib.keys.PublicKey(pubkey)
        return btc_address_obj.address()
    except Exception as e:
        logging.error(f"BTC address derivation error: {e}")
        return None

def derive_solana_address(seed_bytes):
    try:
        if not SolanaClient:
            return None
        seed = hashlib.sha256(seed_bytes).digest()
        keypair = Keypair.from_seed(seed[:32])
        return str(keypair.public_key)
    except Exception as e:
        logging.error(f"Solana address derivation error: {e}")
        return None

def check_eth_balance(address):
    try:
        balance_wei = web3.eth.get_balance(address)
        return web3.fromWei(balance_wei, 'ether')
    except Exception as e:
        logging.error(f"ETH balance fetch error for {address}: {e}")
        return 0

def check_erc20_balance(address, token_contract_address, decimals):
    try:
        erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            }
        ]
        contract = web3.eth.contract(address=Web3.toChecksumAddress(token_contract_address), abi=erc20_abi)
        balance = contract.functions.balanceOf(address).call()
        return balance / (10 ** decimals)
    except Exception as e:
        logging.error(f"ERC20 balance fetch error for {token_contract_address} at {address}: {e}")
        return 0

def check_btc_balance(address):
    try:
        response = requests.get(BTC_API_URL + address)
        data = response.json()
        balance_satoshis = data.get(address, {}).get('final_balance', 0)
        return balance_satoshis / 1e8
    except Exception as e:
        logging.error(f"BTC balance fetch error for {address}: {e}")
        return 0

def check_solana_balance(address):
    if not solana_client:
        return None
    try:
        response = solana_client.get_balance(address)
        if response['result']:
            lamports = response['result']['value']
            return lamports / 1e9  # Convert lamports to SOL
        return 0
    except Exception as e:
        logging.error(f"Solana balance fetch error for {address}: {e}")
        return 0

def get_erc20_token_balance(address, token):
    try:
        erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            }
        ]
        contract = web3.eth.contract(address=Web3.toChecksumAddress(token['address']), abi=erc20_abi)
        balance = contract.functions.balanceOf(address).call()
        return balance / (10 ** token['decimals'])
    except Exception as e:
        logging.error(f"ERC20 token balance fetch error for {token['name']} at {address}: {e}")
        return 0

# Main processing function for each mnemonic
def process_mnemonic(mnemonic):
    results = {}
    try:
        seed_bytes = Mnemonic.to_seed(mnemonic, passphrase="")  # get seed bytes

        # Ethereum
        eth_address = derive_eth_address(seed_bytes)
        if eth_address:
            eth_balance = check_eth_balance(eth_address)
            eth_erc20_balances = {}
            for token in ERC20_TOKENS:
                balance = get_erc20_token_balance(eth_address, token)
                eth_erc20_balances[token['name']] = balance
            results['ethereum'] = {
                'address': eth_address,
                'balance': eth_balance,
                'erc20': eth_erc20_balances
            }

        # Bitcoin
        btc_address = derive_btc_address(seed_bytes)
        if btc_address:
            btc_balance = check_btc_balance(btc_address)
            results['bitcoin'] = {
                'address': btc_address,
                'balance': btc_balance
            }

        # Solana
        sol_address = derive_solana_address(seed_bytes)
        if sol_address:
            sol_balance = check_solana_balance(sol_address)
            results['solana'] = {
                'address': sol_address,
                'balance': sol_balance
            }

        return results
    except Exception as e:
        logging.error(f"Error processing mnemonic: {mnemonic} - {e}")
        return None

# Batch processing parameters
BATCH_SIZE = 50
PAUSE_DURATION = 2  # seconds

for i in range(0, len(mnemonics), BATCH_SIZE):
    batch = mnemonics[i:i + BATCH_SIZE]
    for mnemonic in tqdm(batch, desc=f"Processing batch {i // BATCH_SIZE + 1}"):
        result = process_mnemonic(mnemonic)
        if result:
            # Save results to file
            try:
                with open(LOG_FILE, 'a') as f:
                    f.write(f"{mnemonic}: {result}\n")
            except Exception as e:
                logging.error(f"Error writing result for mnemonic: {mnemonic} - {e}")
    time.sleep(PAUSE_DURATION)

print("Processing complete.")
