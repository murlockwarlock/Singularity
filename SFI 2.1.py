import time
import random
import requests
import json
from hexbytes import HexBytes
from web3 import Web3
from colorama import Fore, Style, init

# Инициализация colorama
init(autoreset=True)

# Подключение к RPC
w3 = Web3(Web3.HTTPProvider('https://rpc-testnet.singularityfinance.ai/'))
if not w3.is_connected():
    print(f"{Fore.RED}Не удалось подключиться к сети. Завершение работы.{Style.RESET_ALL}")
    exit()

print(f"{Fore.GREEN}Успешно подключились к сети.{Style.RESET_ALL}")

# Загрузка ABI из файла
def load_abi_from_file(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

abi_data = load_abi_from_file('abi.json')

# Чтение аккаунтов и прокси из файлов
def load_accounts_from_file(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file.readlines()]

def load_proxies_from_file(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file.readlines()]

accounts = load_accounts_from_file('accounts.txt')
proxies = load_proxies_from_file('proxies.txt')

# Константы адресов
CONTRACT_ADDRESS = w3.to_checksum_address("0x22Dbdc9e8dd7C5E409B014BBcb53a3ef39736515")
ROUTER_ADDRESS = w3.to_checksum_address("0xFEccff0ecf1cAa1669A71C5E00b51B48E4CBc6A1")
PAIR_ADDRESS = w3.to_checksum_address("0xcc922d9E5DaB15513c6500B67459502A6C2e0F3C")
AIM_ADDRESS = w3.to_checksum_address("0xAa4aFA7C07405992e3f6799dCC260D389687077a")
TOKEN_ADDRESS = w3.to_checksum_address("0x03a519f1bd19ce974566ba91190b62d5c00e3a81")
WRAPPED_SFI_ADDRESS = w3.to_checksum_address("0x6dC404EFd04B880B0Ab5a26eF461b63A12E3888D")

# Создание контрактов
contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=abi_data['contract'])
pair_contract = w3.eth.contract(address=PAIR_ADDRESS, abi=abi_data['pair'])
router_contract = w3.eth.contract(address=ROUTER_ADDRESS, abi=abi_data['router_full'])
token_contract = w3.eth.contract(address=TOKEN_ADDRESS, abi=abi_data['token'])
swap_contract = w3.eth.contract(address=ROUTER_ADDRESS, abi=abi_data['swap'])
wrapped_sfi_contract = w3.eth.contract(address=WRAPPED_SFI_ADDRESS, abi=abi_data['wsfi'])
aimm_contract = w3.eth.contract(address=AIM_ADDRESS, abi=abi_data['token'])

# Функция для проверки прокси
def check_proxy(proxy):
    try:
        session = requests.Session()
        session.proxies = {'http': proxy, 'https': proxy}
        response = session.get('https://httpbin.org/ip', timeout=30)
        if response.status_code == 200:
            ip_data = response.json()
            proxy_ip = ip_data.get('origin', 'Неизвестен')
            print(f"{Fore.GREEN}✓ Прокси {proxy} работает (IP: {proxy_ip}){Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.YELLOW}⚠ Прокси {proxy} не работает (код: {response.status_code}){Style.RESET_ALL}")
            return False
    except Exception as e:
        print(f"{Fore.RED}✗ Ошибка проверки прокси {proxy}: {e}{Style.RESET_ALL}")
        return False

# Функция для получения резервов пары
def get_reserves():
    reserves = pair_contract.functions.getReserves().call()
    return reserves[0], reserves[1]  # reserve_eth (Wrapped SFI), reserve_aimm (AIMM)

# Функция для генерации случайной суммы
def generate_random_amount():
    return w3.to_wei(random.uniform(0.01, 0.32), 'ether')

# Функция для получения динамической цены газа с увеличением на 30-50%
def get_dynamic_gas_price(w3, increase_factor=1.0):
    base_gas_price = w3.eth.gas_price
    boost_factor = random.uniform(1.3, 1.5)  # +30% до +50%
    dynamic_gas_price = int(base_gas_price * boost_factor * increase_factor)
    print(f"{Fore.CYAN}Текущая цена газа: {w3.from_wei(base_gas_price, 'gwei')} Gwei, применённая: {w3.from_wei(dynamic_gas_price, 'gwei')} Gwei{Style.RESET_ALL}")
    return dynamic_gas_price

# Функция для проверки статуса транзакции
def check_transaction_status(tx_hash, max_checks=5, wait_time=30):
    for attempt in range(max_checks):
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if receipt:
                if receipt.status == 1:
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Транзакция подтверждена. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return True
                else:
                    print(f"{Fore.RED}✗ Транзакция провалилась. Статус: {receipt.status}{Style.RESET_ALL}")
                    return False
            else:
                print(f"{Fore.YELLOW}Проверка {attempt + 1}/{max_checks}: Транзакция ещё не подтверждена, ждем...{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.YELLOW}Проверка {attempt + 1}/{max_checks}: Ошибка проверки: {e}{Style.RESET_ALL}")
        time.sleep(wait_time)
    print(f"{Fore.RED}✗ Транзакция не подтверждена после {max_checks} проверок.{Style.RESET_ALL}")
    return False

# Функция для получения актуального nonce
def get_actual_nonce(address):
    latest_nonce = w3.eth.get_transaction_count(address, 'latest')
    pending_nonce = w3.eth.get_transaction_count(address, 'pending')
    print(f"{Fore.CYAN}Latest nonce: {latest_nonce}, Pending nonce: {pending_nonce}{Style.RESET_ALL}")
    return latest_nonce

# Обновлённые функции с возвратом (tx_hash, updated_nonce)
def send_approve_wrapped_sfi(spender, nonce, private_key, max_retries=3):
    approve_amount = w3.to_wei(10, 'ether')
    gas_increase_factor = 1.0
    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            tx = wrapped_sfi_contract.functions.approve(spender, approve_amount).build_transaction({
                'chainId': 751, 'gas': 100000, 'gasPrice': gas_price, 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция Approve отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Approve для 10 Wrapped SFI подтвержден. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    revert_reason = receipt.get('revertReason', 'Неизвестно') if 'revertReason' in receipt else 'Нет данных'
                    print(f"{Fore.RED}✗ Approve провалился. Хэш: 0x{tx_hash.hex()}, Revert reason: {revert_reason}{Style.RESET_ALL}")
                    raise Exception("Approve transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Approve для 10 Wrapped SFI подтвержден после проверки. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка Approve Wrapped SFI: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для Approve Wrapped SFI.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def send_deposit_transaction(amount, nonce, private_key, max_retries=3):
    gas_increase_factor = 1.0
    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            locking_period = 96 * 24 * 60 * 60
            tx = contract.functions.deposit(amount, locking_period).build_transaction({
                'chainId': 751, 'gas': 2500000, 'gasPrice': gas_price, 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция депозита отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Депозит выполнен. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    revert_reason = receipt.get('revertReason', 'Неизвестно') if 'revertReason' in receipt else 'Нет данных'
                    print(f"{Fore.RED}✗ Депозит провалился. Хэш: 0x{tx_hash.hex()}, Revert reason: {revert_reason}{Style.RESET_ALL}")
                    raise Exception("Deposit transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Депозит выполнен после проверки. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'transfer amount exceeds allowance' in str(e).lower() or 'insufficient allowance' in str(e).lower() or 'revert' in str(e).lower():
                print(f"{Fore.YELLOW}⚠ Депозит провалился из-за недостаточного одобрения. Выполняем Approve...{Style.RESET_ALL}")
                approve_tx, updated_nonce = send_approve_wrapped_sfi(CONTRACT_ADDRESS, nonce, private_key)
                if approve_tx:
                    nonce = updated_nonce + 1
                    random_sleep(10, 30)
                    print(f"{Fore.YELLOW}Повторная попытка депозита после Approve...{Style.RESET_ALL}")
                else:
                    raise Exception("Не удалось выполнить Approve для депозита")
            else:
                print(f"{Fore.RED}✗ Ошибка депозита: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для депозита.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def get_staked_balance(wallet_address):
    try:
        user_info = contract.functions.userInfo(wallet_address).call()
        staked_amount = user_info[0]
        print(f"{Fore.CYAN}Застейканный баланс: {w3.from_wei(staked_amount, 'ether')} Wrapped SFI{Style.RESET_ALL}")
        return staked_amount
    except Exception as e:
        print(f"{Fore.RED}✗ Ошибка при получении застейканного баланса: {e}{Style.RESET_ALL}")
        return 0

def send_withdraw_and_claim_transaction(wallet_address, nonce, private_key, max_retries=3):
    staked_balance = get_staked_balance(wallet_address)
    if staked_balance == 0:
        print(f"{Fore.YELLOW}⚠ Нет застейканных токенов для вывода.{Style.RESET_ALL}")
        return None, nonce

    percentage = random.uniform(0.03, 0.06)
    withdraw_amount = int(staked_balance * percentage)
    print(f"{Fore.CYAN}Выводим {percentage * 100:.2f}%: {w3.from_wei(withdraw_amount, 'ether')} Wrapped SFI{Style.RESET_ALL}")
    gas_increase_factor = 1.0

    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            tx = contract.functions.withdrawAndClaim(withdraw_amount).build_transaction({
                'chainId': 751, 'gas': 2000000, 'gasPrice': gas_price, 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция WithdrawAndClaim отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ WithdrawAndClaim выполнен. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    revert_reason = receipt.get('revertReason', 'Неизвестно') if 'revertReason' in receipt else 'Нет данных'
                    print(f"{Fore.RED}✗ WithdrawAndClaim провалился. Хэш: 0x{tx_hash.hex()}, Revert reason: {revert_reason}{Style.RESET_ALL}")
                    raise Exception("WithdrawAndClaim transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ WithdrawAndClaim выполнен после проверки. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(wallet_address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(wallet_address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка WithdrawAndClaim: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для WithdrawAndClaim.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def send_claim_transaction(nonce, private_key, max_retries=3):
    gas_increase_factor = 1.0
    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            balance = w3.eth.get_balance(w3.eth.account.from_key(private_key).address)
            print(f"{Fore.CYAN}Баланс перед клеймом: {w3.from_wei(balance, 'ether')} ETH{Style.RESET_ALL}")
            tx = contract.functions.claim().build_transaction({
                'chainId': 751, 'gas': 2000000, 'gasPrice': gas_price, 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция Claim отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Claim выполнен. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    revert_reason = receipt.get('revertReason', 'Неизвестно') if 'revertReason' in receipt else 'Нет данных'
                    print(f"{Fore.RED}✗ Claim провалился. Хэш: 0x{tx_hash.hex()}, Revert reason: {revert_reason}{Style.RESET_ALL}")
                    raise Exception("Claim transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Claim выполнен после проверки. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка Claim: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для Claim.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def send_erc20_transaction(to_address, amount, nonce, private_key, max_retries=3):
    gas_increase_factor = 1.0
    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            tx = token_contract.functions.transfer(to_address, amount).build_transaction({
                'chainId': 751, 'gas': 100000, 'gasPrice': gas_price, 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция отправки токенов отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Токены отправлены. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    revert_reason = receipt.get('revertReason', 'Неизвестно') if 'revertReason' in receipt else 'Нет данных'
                    print(f"{Fore.RED}✗ Отправка токенов провалилась. Хэш: 0x{tx_hash.hex()}, Revert reason: {revert_reason}{Style.RESET_ALL}")
                    raise Exception("Transfer transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Токены отправлены после проверки. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка отправки токенов: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для отправки токенов.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def send_swap_transaction(nonce, eth_amount, private_key, max_retries=3):
    gas_increase_factor = 1.0
    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            amount_out_min = 3285945906750451
            path = [w3.to_checksum_address("0x6dC404EFd04B880B0Ab5a26eF461b63A12E3888D"), AIM_ADDRESS]
            to = w3.eth.account.from_key(private_key).address
            deadline = 115792089237316195423570985008687907853269984665640564039457584007913129639935

            tx = swap_contract.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
                amount_out_min, path, to, deadline
            ).build_transaction({
                'chainId': 751, 'gas': 2000000, 'gasPrice': gas_price, 'nonce': nonce, 'value': eth_amount
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция свапа отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Свап выполнен. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    revert_reason = receipt.get('revertReason', 'Неизвестно') if 'revertReason' in receipt else 'Нет данных'
                    print(f"{Fore.RED}✗ Свап провалился. Хэш: 0x{tx_hash.hex()}, Revert reason: {revert_reason}{Style.RESET_ALL}")
                    raise Exception("Swap transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Свап выполнен после проверки. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка свапа: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для свапа.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def send_approve_transaction(nonce, private_key, amount=1000000, max_retries=3):
    gas_increase_factor = 1.0
    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            tx = aimm_contract.functions.approve(ROUTER_ADDRESS, w3.to_wei(amount, 'ether')).build_transaction({
                'chainId': 751, 'gas': 100000, 'gasPrice': gas_price, 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция Approve отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Approve для {amount} AIMM подтвержден. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    revert_reason = receipt.get('revertReason', 'Неизвестно') if 'revertReason' in receipt else 'Нет данных'
                    print(f"{Fore.RED}✗ Approve провалился. Хэш: 0x{tx_hash.hex()}, Revert reason: {revert_reason}{Style.RESET_ALL}")
                    raise Exception("Approve transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Approve для {amount} AIMM подтвержден после проверки. Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка Approve: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для Approve.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def send_add_liquidity_eth_transaction(nonce, private_key, max_retries=3):
    gas_increase_factor = 1.0
    for attempt in range(max_retries):
        gas_price = get_dynamic_gas_price(w3, gas_increase_factor)
        print(f"{Fore.CYAN}Используемый nonce: {nonce}{Style.RESET_ALL}")
        try:
            reserve_eth, reserve_aimm = get_reserves()
            print(f"{Fore.CYAN}Резервы пула: Wrapped SFI = {w3.from_wei(reserve_eth, 'ether')}, AIMM = {w3.from_wei(reserve_aimm, 'ether')}{Style.RESET_ALL}")
            aimm_balance = aimm_contract.functions.balanceOf(w3.eth.account.from_key(private_key).address).call()
            print(f"{Fore.CYAN}Баланс AIMM: {w3.from_wei(aimm_balance, 'ether')} AIMM{Style.RESET_ALL}")
            wsfi_balance = wrapped_sfi_contract.functions.balanceOf(w3.eth.account.from_key(private_key).address).call()
            print(f"{Fore.CYAN}Баланс Wrapped SFI: {w3.from_wei(wsfi_balance, 'ether')} WSFI{Style.RESET_ALL}")

            if aimm_balance == 0 or wsfi_balance == 0:
                print(f"{Fore.YELLOW}⚠ Баланс AIMM или WSFI равен 0. Пропускаем добавление ликвидности.{Style.RESET_ALL}")
                return None, nonce

            percentage = random.uniform(0.10, 0.15)
            aimm_amount_wei = int(aimm_balance * percentage)
            aimm_amount = w3.from_wei(aimm_amount_wei, 'ether')
            print(f"{Fore.CYAN}Используем {percentage * 100:.2f}% баланса AIMM: {aimm_amount} AIMM{Style.RESET_ALL}")

            if reserve_aimm > 0 and reserve_eth > 0:
                eth_amount_wei = (aimm_amount_wei * reserve_eth) // reserve_aimm
                eth_amount = w3.from_wei(eth_amount_wei, 'ether')
            else:
                print(f"{Fore.YELLOW}⚠ Резервы пула некорректны. Используем случайное значение Wrapped SFI.{Style.RESET_ALL}")
                eth_amount_wei = w3.to_wei(random.uniform(0.001, 0.028), 'ether')
                eth_amount = w3.from_wei(eth_amount_wei, 'ether')

            if eth_amount_wei > wsfi_balance:
                print(f"{Fore.YELLOW}⚠ Требуется больше WSFI ({eth_amount}) чем доступно ({w3.from_wei(wsfi_balance, 'ether')}). Корректируем...{Style.RESET_ALL}")
                eth_amount_wei = wsfi_balance
                aimm_amount_wei = (eth_amount_wei * reserve_aimm) // reserve_eth if reserve_eth > 0 else aimm_amount_wei
                aimm_amount = w3.from_wei(aimm_amount_wei, 'ether')
                eth_amount = w3.from_wei(eth_amount_wei, 'ether')
                print(f"{Fore.CYAN}Скорректировано: Wrapped SFI = {eth_amount}, AIMM = {aimm_amount}{Style.RESET_ALL}")

            print(f"{Fore.CYAN}Добавляем: Wrapped SFI = {eth_amount}, AIMM = {aimm_amount}{Style.RESET_ALL}")
            amount_token_min = aimm_amount_wei * 95 // 100
            amount_eth_min = eth_amount_wei * 95 // 100
            to = w3.eth.account.from_key(private_key).address
            deadline = 115792089237316195423570985008687907853269984665640564039457584007913129639935

            tx = router_contract.functions.addLiquidityETH(
                AIM_ADDRESS, aimm_amount_wei, amount_token_min, amount_eth_min, to, deadline
            ).build_transaction({
                'chainId': 751, 'gas': 300000, 'gasPrice': gas_price, 'nonce': nonce, 'value': eth_amount_wei
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.CYAN}✅ Транзакция addLiquidityETH отправлена. Хэш: 0x{tx_hash.hex()}{Style.RESET_ALL}")

            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt.status == 1:
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Ликвидность добавлена (Wrapped SFI = {eth_amount}, AIMM = {aimm_amount}). Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    print(f"{Fore.RED}✗ Ликвидность не добавлена. Статус: {receipt.status}{Style.RESET_ALL}")
                    raise Exception("Liquidity transaction failed")
            except Exception as timeout_error:
                print(f"{Fore.YELLOW}⚠ Тайм-аут 120 секунд для транзакции 0x{tx_hash.hex()}. Проверяем статус...{Style.RESET_ALL}")
                if check_transaction_status(tx_hash):
                    tx_info = w3.eth.get_transaction(tx_hash)
                    actual_nonce = tx_info['nonce']
                    print(f"{Fore.CYAN}Фактический nonce: {actual_nonce}{Style.RESET_ALL}")
                    if actual_nonce != nonce:
                        print(f"{Fore.YELLOW}⚠ Несоответствие nonce: ожидалось {nonce}, фактически {actual_nonce}{Style.RESET_ALL}")
                        return tx_hash, actual_nonce
                    tx_hash_link = f"https://explorer-testnet.singularityfinance.ai/tx/0x{tx_hash.hex()}"
                    print(f"{Fore.GREEN}✓ Ликвидность добавлена после проверки (Wrapped SFI = {eth_amount}, AIMM = {aimm_amount}). Хэш: {tx_hash_link}{Style.RESET_ALL}")
                    return tx_hash, nonce
                else:
                    raise Exception("Транзакция не подтверждена после проверки")

        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            elif 'replacement transaction underpriced' in str(e):
                print(f"{Fore.YELLOW}⚠ Цена газа слишком низкая, увеличиваем на 20% (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                gas_increase_factor *= 1.2
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка addLiquidityETH: {e}{Style.RESET_ALL}")
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}Повторяем через 10 секунд...{Style.RESET_ALL}")
                    time.sleep(10)
                else:
                    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для addLiquidityETH.{Style.RESET_ALL}")
                    return None, nonce
    return None, nonce

def random_sleep(min_time, max_time):
    sleep_time = random.randint(min_time, max_time)
    print(f"{Fore.CYAN}Пауза на {sleep_time} секунд...{Style.RESET_ALL}")
    time.sleep(sleep_time)

def get_wallet_stats(wallet_address):
    try:
        tx_count = w3.eth.get_transaction_count(wallet_address)
        balance = w3.eth.get_balance(wallet_address)
        print(f"{Fore.CYAN}Статистика кошелька {wallet_address}:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Количество транзакций: {tx_count}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Баланс: {w3.from_wei(balance, 'ether')} ETH{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}✗ Ошибка при получении статистики кошелька: {e}{Style.RESET_ALL}")

# Основной процесс
for i in range(min(len(accounts), len(proxies))):
    private_key = accounts[i]
    proxy = proxies[i]

    account = w3.eth.account.from_key(private_key)
    address = account.address

    print(f"{Fore.MAGENTA}=== Обработка аккаунта: {address} ==={Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}Используемый прокси: {proxy}{Style.RESET_ALL}")

    max_retries = 3
    proxy_works = False
    for attempt in range(max_retries):
        print(f"{Fore.CYAN}Попытка {attempt + 1} из {max_retries} проверки прокси...{Style.RESET_ALL}")
        if check_proxy(proxy):
            proxy_works = True
            break
        time.sleep(2)
    if not proxy_works:
        print(f"{Fore.RED}✗ Прокси {proxy} не работает после {max_retries} попыток. Пропускаем аккаунт.{Style.RESET_ALL}")
        continue

    nonce = get_actual_nonce(address)

    # 1. Выполняем свап 3 раза
    print(f"{Fore.BLUE}=== Этап 1: Свапы ==={Style.RESET_ALL}")
    for j in range(3):
        swap_amount = generate_random_amount()
        print(f"{Fore.CYAN}Запуск свапа {j + 1}/3 на {w3.from_wei(swap_amount, 'ether')} ETH...{Style.RESET_ALL}")
        tx_hash, updated_nonce = send_swap_transaction(nonce, swap_amount, private_key)
        if tx_hash:
            nonce = updated_nonce + 1
            print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
        else:
            break
        random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Свапы завершены ==={Style.RESET_ALL}")

    # 2. Добавляем ликвидность
    print(f"{Fore.BLUE}=== Этап 2: Добавление ликвидности ==={Style.RESET_ALL}")
    tx_hash, updated_nonce = send_add_liquidity_eth_transaction(nonce, private_key)
    if not tx_hash:
        print(f"{Fore.YELLOW}Ликвидность не добавлена, выполняем Approve...{Style.RESET_ALL}")
        tx_hash, updated_nonce = send_approve_transaction(nonce, private_key, amount=1000)
        if tx_hash:
            nonce = updated_nonce + 1
            print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
        random_sleep(10, 45)
        print(f"{Fore.YELLOW}Повторная попытка добавления ликвидности...{Style.RESET_ALL}")
        tx_hash, updated_nonce = send_add_liquidity_eth_transaction(nonce, private_key)
        if tx_hash:
            nonce = updated_nonce + 1
            print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
    else:
        nonce = updated_nonce + 1
        print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
    random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Добавление ликвидности завершено ==={Style.RESET_ALL}")

    # 3. Выполняем депозиты
    print(f"{Fore.BLUE}=== Этап 3: Депозиты ==={Style.RESET_ALL}")
    amount1 = generate_random_amount()
    print(f"{Fore.CYAN}Баланс Wrapped SFI: {w3.from_wei(wrapped_sfi_contract.functions.balanceOf(address).call(), 'ether')} ETH{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Текущий allowance: {w3.from_wei(wrapped_sfi_contract.functions.allowance(address, CONTRACT_ADDRESS).call(), 'ether')} ETH{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Отправка первого депозита на {w3.from_wei(amount1, 'ether')} ETH...{Style.RESET_ALL}")
    tx_hash1, updated_nonce = send_deposit_transaction(amount1, nonce, private_key)
    if tx_hash1:
        nonce = updated_nonce + 1
        print(f"{Fore.GREEN}✓ Первый депозит отправлен. Хэш: 0x{tx_hash1.hex()}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
    random_sleep(10, 45)

    amount2 = generate_random_amount()
    print(f"{Fore.CYAN}Баланс Wrapped SFI: {w3.from_wei(wrapped_sfi_contract.functions.balanceOf(address).call(), 'ether')} ETH{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Текущий allowance: {w3.from_wei(wrapped_sfi_contract.functions.allowance(address, CONTRACT_ADDRESS).call(), 'ether')} ETH{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Отправка второго депозита на {w3.from_wei(amount2, 'ether')} ETH...{Style.RESET_ALL}")
    tx_hash2, updated_nonce = send_deposit_transaction(amount2, nonce, private_key)
    if tx_hash2:
        nonce = updated_nonce + 1
        print(f"{Fore.GREEN}✓ Второй депозит отправлен. Хэш: 0x{tx_hash2.hex()}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
    random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Депозиты завершены ==={Style.RESET_ALL}")

    # 4. Отправляем токены
    print(f"{Fore.BLUE}=== Этап 4: Отправка токенов ==={Style.RESET_ALL}")
    for k in range(3):
        eth_amount = random.uniform(0.01, 0.99)
        amount = w3.to_wei(eth_amount, 'ether')
        print(f"{Fore.CYAN}Отправка токенов {k + 1}/3 на {eth_amount:.2f} ETH ({amount} wei)...{Style.RESET_ALL}")
        tx_hash, updated_nonce = send_erc20_transaction(address, amount, nonce, private_key)
        if tx_hash:
            nonce = updated_nonce + 1
            print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
        random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Отправка токенов завершена ==={Style.RESET_ALL}")

    # 5. Выполняем withdrawAndClaim
    print(f"{Fore.BLUE}=== Этап 5: WithdrawAndClaim ==={Style.RESET_ALL}")
    tx_hash, updated_nonce = send_withdraw_and_claim_transaction(address, nonce, private_key)
    if tx_hash:
        nonce = updated_nonce + 1
        print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
    random_sleep(10, 45)
    print(f"{Fore.BLUE}=== WithdrawAndClaim завершён ==={Style.RESET_ALL}")

    # 6. Выполняем клейм 2 раза
    print(f"{Fore.BLUE}=== Этап 6: Клейм ==={Style.RESET_ALL}")
    for _ in range(2):
        print(f"{Fore.CYAN}Отправка транзакции для claim...{Style.RESET_ALL}")
        tx_hash, updated_nonce = send_claim_transaction(nonce, private_key)
        if tx_hash:
            nonce = updated_nonce + 1
            print(f"{Fore.CYAN}Nonce обновлён до: {nonce}{Style.RESET_ALL}")
        random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Клейм завершён ==={Style.RESET_ALL}")

    # Вывод статистики кошелька
    get_wallet_stats(address)

    random_sleep(30, 60)
    print(f"{Fore.MAGENTA}=== Обработка аккаунта {address} завершена ==={Style.RESET_ALL}")
