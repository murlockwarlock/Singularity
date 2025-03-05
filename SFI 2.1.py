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

# Константы адресов с преобразованием в формат контрольной суммы
CONTRACT_ADDRESS = w3.to_checksum_address("0x22Dbdc9e8dd7C5E409B014BBcb53a3ef39736515")
ROUTER_ADDRESS = w3.to_checksum_address("0xFEccff0ecf1cAa1669A71C5E00b51B48E4CBc6A1")
PAIR_ADDRESS = w3.to_checksum_address("0xcc922d9E5DaB15513c6500B67459502A6C2e0F3C")
AIM_ADDRESS = w3.to_checksum_address("0xAa4aFA7C07405992e3f6799dCC260D389687077a")
TOKEN_ADDRESS = w3.to_checksum_address("0x03a519f1bd19ce974566ba91190b62d5c00e3a81")

# Создание контрактов
contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=abi_data['contract'])
pair_contract = w3.eth.contract(address=PAIR_ADDRESS, abi=abi_data['pair'])
router_contract = w3.eth.contract(address=ROUTER_ADDRESS, abi=abi_data['router'])
token_contract = w3.eth.contract(address=TOKEN_ADDRESS, abi=abi_data['token'])
swap_contract = w3.eth.contract(address=ROUTER_ADDRESS, abi=abi_data['swap'])

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
    return reserves[0], reserves[1]  # reserve_eth, reserve_aimm

# Функция для генерации случайной суммы
def generate_random_amount():
    return w3.to_wei(random.uniform(0.01, 0.32), 'ether')

# Функция для отправки депозита с обработкой nonce
def send_deposit_transaction(amount, nonce, private_key, max_retries=3):
    for attempt in range(max_retries):
        try:
            locking_period = 96 * 24 * 60 * 60
            tx = contract.functions.deposit(amount, locking_period).build_transaction({
                'chainId': 751, 'gas': 2000000, 'gasPrice': w3.to_wei('20', 'gwei'), 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            return tx_hash
        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка депозита: {e}{Style.RESET_ALL}")
                return None
    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для депозита.{Style.RESET_ALL}")
    return None

# Функция для withdrawAndClaim
def send_withdraw_and_claim_transaction(amount, nonce, private_key, max_retries=3):
    for attempt in range(max_retries):
        try:
            tx = contract.functions.withdrawAndClaim(amount).build_transaction({
                'chainId': 751, 'gas': 2000000, 'gasPrice': w3.to_wei('20', 'gwei'), 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.GREEN}✓ WithdrawAndClaim выполнен. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
            return tx_hash
        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка WithdrawAndClaim: {e}{Style.RESET_ALL}")
                return None
    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для WithdrawAndClaim.{Style.RESET_ALL}")
    return None

# Функция для клейма
def send_claim_transaction(nonce, private_key, max_retries=3):
    for attempt in range(max_retries):
        try:
            balance = w3.eth.get_balance(w3.eth.account.from_key(private_key).address)
            print(f"Баланс перед клеймом: {w3.from_wei(balance, 'ether')} ETH")
            tx = contract.functions.claim().build_transaction({
                'chainId': 751, 'gas': 2000000, 'gasPrice': w3.to_wei('20', 'gwei'), 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.GREEN}✓ Claim выполнен. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
            return tx_hash
        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка Claim: {e}{Style.RESET_ALL}")
                return None
    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для Claim.{Style.RESET_ALL}")
    return None

# Функция для отправки токенов (ERC20)
def send_erc20_transaction(to_address, amount, nonce, private_key, max_retries=3):
    for attempt in range(max_retries):
        try:
            tx = token_contract.functions.transfer(to_address, amount).build_transaction({
                'chainId': 751, 'gas': 100000, 'gasPrice': w3.to_wei('20', 'gwei'), 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.GREEN}✓ Токены отправлены. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
            return tx_hash
        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка отправки токенов: {e}{Style.RESET_ALL}")
                return None
    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для отправки токенов.{Style.RESET_ALL}")
    return None

# Функция для свапа
def send_swap_transaction(nonce, eth_amount, private_key, max_retries=3):
    for attempt in range(max_retries):
        try:
            amount_out_min = 3285945906750451
            path = [w3.to_checksum_address("0x6dC404EFd04B880B0Ab5a26eF461b63A12E3888D"), AIM_ADDRESS]
            to = w3.eth.account.from_key(private_key).address
            deadline = 115792089237316195423570985008687907853269984665640564039457584007913129639935

            tx = swap_contract.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
                amount_out_min, path, to, deadline
            ).build_transaction({
                'chainId': 751, 'gas': 2000000, 'gasPrice': w3.to_wei('20', 'gwei'), 'nonce': nonce, 'value': eth_amount
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"{Fore.GREEN}✓ Свап выполнен. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
            return tx_hash
        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка свапа: {e}{Style.RESET_ALL}")
                return None
    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для свапа.{Style.RESET_ALL}")
    return None

# Функция Approve для токена AIMM
def send_approve_transaction(nonce, private_key, amount=1000000, max_retries=3):
    for attempt in range(max_retries):
        try:
            tx = token_contract.functions.approve(ROUTER_ADDRESS, w3.to_wei(amount, 'ether')).build_transaction({
                'chainId': 751, 'gas': 100000, 'gasPrice': w3.to_wei('20', 'gwei'), 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                print(f"{Fore.GREEN}✓ Approve для {amount} AIMM подтвержден. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
                return tx_hash
            else:
                print(f"{Fore.RED}✗ Approve для {amount} AIMM провалился. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
                raise Exception("Approve transaction failed")
        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка Approve: {e}{Style.RESET_ALL}")
                return None
    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для Approve.{Style.RESET_ALL}")
    return None

# Функция addLiquidityETH
def send_add_liquidity_eth_transaction(nonce, private_key, max_retries=3):
    for attempt in range(max_retries):
        try:
            reserve_eth, reserve_aimm = get_reserves()
            print(f"Резервы пула: ETH = {w3.from_wei(reserve_eth, 'ether')}, AIMM = {w3.from_wei(reserve_aimm, 'ether')}")

            eth_amount = random.uniform(0.001, 0.028)
            eth_amount_wei = w3.to_wei(eth_amount, 'ether')
            aimm_amount_wei = eth_amount_wei * reserve_aimm // reserve_eth if reserve_eth > 0 else eth_amount_wei
            aimm_amount = w3.from_wei(aimm_amount_wei, 'ether')
            print(f"Добавляем: ETH = {eth_amount}, AIMM = {aimm_amount}")

            amount_token_min = aimm_amount_wei * 95 // 100
            amount_eth_min = eth_amount_wei * 95 // 100
            to = w3.eth.account.from_key(private_key).address
            deadline = 115792089237316195423570985008687907853269984665640564039457584007913129639935

            tx = router_contract.functions.addLiquidityETH(
                AIM_ADDRESS, aimm_amount_wei, amount_token_min, amount_eth_min, to, deadline
            ).build_transaction({
                'chainId': 751, 'gas': 300000, 'gasPrice': w3.to_wei('20', 'gwei'), 'nonce': nonce, 'value': eth_amount_wei
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                print(f"{Fore.GREEN}✓ Ликвидность добавлена (ETH = {eth_amount}, AIMM = {aimm_amount}). Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
                return tx_hash
            else:
                print(f"{Fore.YELLOW}⚠ Ликвидность не добавлена. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
                raise Exception("Liquidity transaction failed")
        except Exception as e:
            if 'nonce too low' in str(e):
                print(f"{Fore.YELLOW}⚠ Nonce слишком низкий, обновляем и повторяем (попытка {attempt + 1}/{max_retries})...{Style.RESET_ALL}")
                nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(private_key).address, 'pending')
            else:
                print(f"{Fore.RED}✗ Ошибка addLiquidityETH: {e}{Style.RESET_ALL}")
                return None
    print(f"{Fore.RED}✗ Превышено максимальное количество попыток для addLiquidityETH.{Style.RESET_ALL}")
    return None

# Функция для случайной паузы
def random_sleep(min_time, max_time):
    sleep_time = random.randint(min_time, max_time)
    print(f"{Fore.CYAN}Пауза на {sleep_time} секунд...{Style.RESET_ALL}")
    time.sleep(sleep_time)

# Основной процесс
for i in range(min(len(accounts), len(proxies))):
    private_key = accounts[i]
    proxy = proxies[i]

    account = w3.eth.account.from_key(private_key)
    address = account.address

    print(f"{Fore.MAGENTA}=== Обработка аккаунта: {address} ==={Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}Используемый прокси: {proxy}{Style.RESET_ALL}")

    # Проверка прокси
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

    nonce = w3.eth.get_transaction_count(address, 'pending')  # Используем 'pending' для актуального nonce

    # 1. Выполняем свап 3 раза
    print(f"{Fore.BLUE}=== Этап 1: Свапы ==={Style.RESET_ALL}")
    for j in range(3):
        swap_amount = generate_random_amount()
        print(f"Запуск свапа {j + 1}/3 на {w3.from_wei(swap_amount, 'ether')} ETH...")
        tx_hash = send_swap_transaction(nonce, swap_amount, private_key)
        if tx_hash:
            nonce += 1
        else:
            break
        random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Свапы завершены ==={Style.RESET_ALL}")

    # 2. Добавляем ликвидность
    print(f"{Fore.BLUE}=== Этап 2: Добавление ликвидности ==={Style.RESET_ALL}")
    tx_hash = send_add_liquidity_eth_transaction(nonce, private_key)
    if not tx_hash:
        print("Ликвидность не добавлена, выполняем Approve...")
        tx_hash = send_approve_transaction(nonce, private_key, amount=1000)
        if tx_hash:
            nonce += 1
        random_sleep(10, 45)
        print("Повторная попытка добавления ликвидности...")
        tx_hash = send_add_liquidity_eth_transaction(nonce, private_key)
        if tx_hash:
            nonce += 1
    random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Добавление ликвидности завершено ==={Style.RESET_ALL}")

    # 3. Выполняем депозиты
    print(f"{Fore.BLUE}=== Этап 3: Депозиты ==={Style.RESET_ALL}")
    amount1 = generate_random_amount()
    print(f"Отправка первого депозита на {w3.from_wei(amount1, 'ether')} ETH...")
    tx_hash1 = send_deposit_transaction(amount1, nonce, private_key)
    if tx_hash1:
        print(f"{Fore.GREEN}✓ Первый депозит отправлен. Хэш: {tx_hash1.hex()}{Style.RESET_ALL}")
        nonce += 1
    random_sleep(10, 45)

    amount2 = generate_random_amount()
    print(f"Отправка второго депозита на {w3.from_wei(amount2, 'ether')} ETH...")
    tx_hash2 = send_deposit_transaction(amount2, nonce, private_key)
    if tx_hash2:
        print(f"{Fore.GREEN}✓ Второй депозит отправлен. Хэш: {tx_hash2.hex()}{Style.RESET_ALL}")
        nonce += 1
    random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Депозиты завершены ==={Style.RESET_ALL}")

    # 4. Отправляем токены
    print(f"{Fore.BLUE}=== Этап 4: Отправка токенов ==={Style.RESET_ALL}")
    for k in range(3):
        eth_amount = random.uniform(0.01, 0.99)
        amount = w3.to_wei(eth_amount, 'ether')
        print(f"Отправка токенов {k + 1}/3 на {eth_amount:.2f} ETH ({amount} wei)...")
        tx_hash = send_erc20_transaction(address, amount, nonce, private_key)
        if tx_hash:
            nonce += 1
        random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Отправка токенов завершена ==={Style.RESET_ALL}")

    # 5. Выполняем withdrawAndClaim
    print(f"{Fore.BLUE}=== Этап 5: WithdrawAndClaim ==={Style.RESET_ALL}")
    withdraw_amount = generate_random_amount()
    print(f"Отправка withdrawAndClaim на {w3.from_wei(withdraw_amount, 'ether')} ETH...")
    tx_hash = send_withdraw_and_claim_transaction(withdraw_amount, nonce, private_key)
    if tx_hash:
        nonce += 1
    random_sleep(10, 45)
    print(f"{Fore.BLUE}=== WithdrawAndClaim завершён ==={Style.RESET_ALL}")

    # 6. Выполняем клейм 2 раза
    print(f"{Fore.BLUE}=== Этап 6: Клейм ==={Style.RESET_ALL}")
    for _ in range(2):
        print("Отправка транзакции для claim...")
        tx_hash = send_claim_transaction(nonce, private_key)
        if tx_hash:
            nonce += 1
        random_sleep(10, 45)
    print(f"{Fore.BLUE}=== Клейм завершён ==={Style.RESET_ALL}")

    # Пауза между аккаунтами
    random_sleep(30, 60)
    print(f"{Fore.MAGENTA}=== Обработка аккаунта {address} завершена ==={Style.RESET_ALL}")
