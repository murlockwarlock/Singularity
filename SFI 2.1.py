import time
import random
import requests
from hexbytes import HexBytes
from web3 import Web3
from colorama import Fore, Style, init

# Инициализация colorama
init(autoreset=True)

# Подключаемся к RPC
w3 = Web3(Web3.HTTPProvider('https://rpc-testnet.singularityfinance.ai/'))

# Проверка подключения
if w3.is_connected():
    print("Успешно подключились к сети")
else:
    print("Не удалось подключиться к сети")
    exit()


# Чтение аккаунтов и прокси из файлов
def load_accounts_from_file(file_path):
    with open(file_path, 'r') as file:
        accounts = [line.strip() for line in file.readlines()]
    return accounts


def load_proxies_from_file(file_path):
    with open(file_path, 'r') as file:
        proxies = [line.strip() for line in file.readlines()]
    return proxies


accounts = load_accounts_from_file("accounts.txt")
proxies = load_proxies_from_file("proxies.txt")

# Адреса контрактов
router_address = "0xFEccff0ecf1cAa1669A71C5E00b51B48E4CBc6A1"
pair_address = "0xcc922d9E5DaB15513c6500B67459502A6C2e0F3C"  # Подтверждённый адрес пары AIMM/ETH
AIM_address = "0xAa4aFA7C07405992e3f6799dCC260D389687077a"  # AIMM токен

# ABI для пары (Uniswap V2-style)
pair_abi = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]

# Контракт пары
pair_contract = w3.eth.contract(address=pair_address, abi=pair_abi)

# Контрактный адрес и ABI основного контракта
contract_address = "0x22Dbdc9e8dd7C5E409B014BBcb53a3ef39736515"
contract_abi = [
    {
        "constant": False,
        "inputs": [
            {"name": "_amount", "type": "uint256"},
            {"name": "_lockingPeriod", "type": "uint256"}
        ],
        "name": "deposit",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_amount", "type": "uint256"}
        ],
        "name": "withdrawAndClaim",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [],
        "name": "claim",
        "outputs": [],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Создание контракта
contract = w3.eth.contract(address=contract_address, abi=contract_abi)


# Функция для проверки прокси
def check_proxy(proxy):
    try:
        session = requests.Session()
        session.proxies = {
            'http': proxy,
            'https': proxy,
        }
        response = session.get('https://httpbin.org/ip', timeout=30)
        if response.status_code == 200:
            print(f"{Fore.GREEN}✓ Прокси {proxy} работает{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.RED}✗ Прокси {proxy} не работает{Style.RESET_ALL}")
            return False
    except Exception as e:
        print(f"{Fore.RED}✗ Ошибка при проверке прокси {proxy}: {e}{Style.RESET_ALL}")
        return False


# Функция для получения резервов пары
def get_reserves():
    reserves = pair_contract.functions.getReserves().call()
    reserve_eth = reserves[0]
    reserve_aimm = reserves[1]
    return reserve_eth, reserve_aimm


# Функция для генерации случайной суммы для депозита
def generate_random_amount():
    eth_amount = random.uniform(0.01, 0.32)
    return w3.to_wei(eth_amount, 'ether')


# Функция для отправки депозита
def send_deposit_transaction(amount, nonce, private_key):
    locking_period = 96 * 24 * 60 * 60
    transaction = contract.functions.deposit(amount, locking_period).build_transaction({
        'chainId': 751,
        'gas': 2000000,
        'gasPrice': w3.to_wei('20', 'gwei'),
        'nonce': nonce,
    })

    signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)
    return tx_hash


# Функция для отправки транзакции withdrawAndClaim
def send_withdraw_and_claim_transaction(amount, nonce, private_key):
    try:
        transaction = contract.functions.withdrawAndClaim(amount).build_transaction({
            'chainId': 751,
            'gas': 2000000,
            'gasPrice': w3.to_wei('20', 'gwei'),
            'nonce': nonce,
        })

        signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)

        print(
            f"{Fore.GREEN}✓ Транзакция для withdrawAndClaim успешно отправлена. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
        return tx_hash

    except Exception as e:
        print(f"{Fore.RED}✗ Ошибка при отправке withdrawAndClaim транзакции: {e}{Style.RESET_ALL}")
        return None


# Функция для отправки клейма
def send_claim_transaction(nonce, private_key):
    try:
        balance = w3.eth.get_balance(w3.eth.account.from_key(private_key).address)
        print(f"Баланс перед клеймом: {w3.from_wei(balance, 'ether')} ETH")

        transaction = contract.functions.claim().build_transaction({
            'chainId': 751,
            'gas': 2000000,
            'gasPrice': w3.to_wei('20', 'gwei'),
            'nonce': nonce,
        })

        signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)

        print(f"{Fore.GREEN}✓ Транзакция для claim успешно отправлена. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
        return tx_hash

    except Exception as e:
        print(f"{Fore.RED}✗ Ошибка при отправке claim транзакции: {e}{Style.RESET_ALL}")
        return None


# Функция для отправки токенов (ERC20)
def send_erc20_transaction(token_address, to_address, amount, nonce, private_key):
    token_address = Web3.to_checksum_address(token_address)
    token_abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"}
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]

    token_contract = w3.eth.contract(address=token_address, abi=token_abi)
    transaction = token_contract.functions.transfer(to_address, amount).build_transaction({
        'chainId': 751,
        'gas': 100000,
        'gasPrice': w3.to_wei('20', 'gwei'),
        'nonce': nonce,
    })

    signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)
    tx_hash: HexBytes = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)

    print(f"{Fore.GREEN}✓ Токены отправлены. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
    return tx_hash


# Функция для свапа
def send_swap_transaction(nonce, eth_amount, private_key):
    swap_contract_address = "0xFEccff0ecf1cAa1669A71C5E00b51B48E4CBc6A1"
    swap_contract_abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"},
                {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}
            ],
            "name": "swapExactETHForTokensSupportingFeeOnTransferTokens",
            "outputs": [{"name": "", "type": "uint256[]"}],
            "payable": True,
            "stateMutability": "payable",
            "type": "function"
        }
    ]

    swap_contract = w3.eth.contract(address=swap_contract_address, abi=swap_contract_abi)

    amount_out_min = 3285945906750451
    path = ["0x6dC404EFd04B880B0Ab5a26eF461b63A12E3888D", "0xAa4aFA7C07405992e3f6799dCC260D389687077a"]
    to = w3.eth.account.from_key(private_key).address
    deadline = 115792089237316195423570985008687907853269984665640564039457584007913129639935

    transaction = swap_contract.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
        amount_out_min, path, to, deadline).build_transaction({
        'chainId': 751,
        'gas': 2000000,
        'gasPrice': w3.to_wei('20', 'gwei'),
        'nonce': nonce,
        'value': eth_amount
    })

    signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)

    print(f"{Fore.GREEN}✓ Свап выполнен. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
    return tx_hash


# Функция Approve для токена AIMM
def send_approve_transaction(nonce, private_key, amount=1000000):
    token_address = "0xAa4aFA7C07405992e3f6799dCC260D389687077a"  # AIMM
    token_abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]

    token_contract = w3.eth.contract(address=token_address, abi=token_abi)
    spender = "0xFEccff0ecf1cAa1669A71C5E00b51B48E4CBc6A1"
    amount_wei = w3.to_wei(amount, 'ether')

    transaction = token_contract.functions.approve(spender, amount_wei).build_transaction({
        'chainId': 751,
        'gas': 100000,
        'gasPrice': w3.to_wei('20', 'gwei'),
        'nonce': nonce,
    })

    signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)

    print(f"{Fore.GREEN}✓ Approve для {amount} AIMM отправлен. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status == 1:
        print(f"{Fore.GREEN}✓ Approve для {amount} AIMM подтвержден{Style.RESET_ALL}")
        return tx_hash
    else:
        print(f"{Fore.RED}✗ Approve для {amount} AIMM провалился{Style.RESET_ALL}")
        raise Exception("Approve transaction failed")


# Функция addLiquidityETH с рандомным количеством ETH
def send_add_liquidity_eth_transaction(nonce, private_key):
    router_abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "token", "type": "address"},
                {"name": "amountTokenDesired", "type": "uint256"},
                {"name": "amountTokenMin", "type": "uint256"},
                {"name": "amountETHMin", "type": "uint256"},
                {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}
            ],
            "name": "addLiquidityETH",
            "outputs": [],
            "payable": True,
            "stateMutability": "payable",
            "type": "function"
        }
    ]

    router_contract = w3.eth.contract(address=router_address, abi=router_abi)

    reserve_eth, reserve_aimm = get_reserves()
    print(f"Резервы пула: ETH = {w3.from_wei(reserve_eth, 'ether')}, AIMM = {w3.from_wei(reserve_aimm, 'ether')}")

    eth_amount = random.uniform(0.001, 0.028)
    eth_amount_wei = w3.to_wei(eth_amount, 'ether')

    aimm_amount_wei = eth_amount_wei * reserve_aimm // reserve_eth
    aimm_amount = w3.from_wei(aimm_amount_wei, 'ether')
    print(f"Добавляем: ETH = {eth_amount}, AIMM = {aimm_amount}")

    amount_token_min = aimm_amount_wei * 95 // 100
    amount_eth_min = eth_amount_wei * 95 // 100

    token = "0xAa4aFA7C07405992e3f6799dCC260D389687077a"
    to = w3.eth.account.from_key(private_key).address
    deadline = 115792089237316195423570985008687907853269984665640564039457584007913129639935

    transaction = router_contract.functions.addLiquidityETH(
        token, aimm_amount_wei, amount_token_min, amount_eth_min, to, deadline
    ).build_transaction({
        'chainId': 751,
        'gas': 300000,
        'gasPrice': w3.to_wei('20', 'gwei'),
        'nonce': nonce,
        'value': eth_amount_wei
    })

    try:
        signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_transaction.raw_transaction)
        print(f"Транзакция добавления ликвидности отправлена. Хэш: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 1:
            print(
                f"{Fore.GREEN}✓ Добавлена ликвидность (ETH = {eth_amount}, AIMM = {aimm_amount}). Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
            return tx_hash, True
        else:
            print(f"{Fore.RED}✗ Транзакция добавления ликвидности провалилась. Хэш: {tx_hash.hex()}{Style.RESET_ALL}")
            return tx_hash, False
    except Exception as e:
        print(f"{Fore.RED}✗ Ошибка при отправке транзакции addLiquidityETH: {e}{Style.RESET_ALL}")
        return None, False


# Функция для случайной паузы
def random_sleep(min_time, max_time):
    sleep_time = random.randint(min_time, max_time)
    print(f"Пауза на {sleep_time} секунд...")
    time.sleep(sleep_time)


# Основной процесс с мультиаккаунтами и прокси
for i in range(min(len(accounts), len(proxies))):
    private_key = accounts[i]
    proxy = proxies[i]

    account = w3.eth.account.from_key(private_key)
    address = account.address

    print(f"Используем аккаунт: {address}")
    print(f"Используем прокси: {proxy}")

    # Проверка прокси с повторными попытками
    max_retries = 3
    proxy_works = False
    for attempt in range(max_retries):
        print(f"Попытка {attempt + 1} проверить прокси...")
        if check_proxy(proxy):
            proxy_works = True
            break
        time.sleep(2)
    if not proxy_works:
        print(
            f"{Fore.RED}✗ Прокси {proxy} не работает после {max_retries} попыток, пропускаем аккаунт {address}{Style.RESET_ALL}")
        continue

    # Настраиваем сессию с прокси (хотя для Web3 она не используется напрямую)
    session = requests.Session()
    session.proxies = {
        'http': proxy,
        'https': proxy,
    }

    nonce = w3.eth.get_transaction_count(address, 'latest')

    # Добавляем ликвидность с проверкой на провал
    print("Добавляем ликвидность AIMM + ETH...")
    tx_hash, success = send_add_liquidity_eth_transaction(nonce, private_key)
    nonce += 1
    if not success:
        print("Транзакция addLiquidityETH провалилась, выполняем approve для 1000 AIMM...")
        tx_hash = send_approve_transaction(nonce, private_key, amount=1000)
        nonce += 1
        random_sleep(10, 45)
        print("Повторная попытка добавить ликвидность AIMM + ETH...")
        tx_hash, _ = send_add_liquidity_eth_transaction(nonce, private_key)
        nonce += 1
    random_sleep(10, 45)

    # Отправляем депозит 1
    amount1 = generate_random_amount()
    print(f"Отправка первого депозита на {w3.from_wei(amount1, 'ether')} ETH...")
    tx_hash1 = send_deposit_transaction(amount1, nonce, private_key)
    print(f"{Fore.GREEN}✓ Первый депозит отправлен. Хэш: {tx_hash1.hex()}{Style.RESET_ALL}")
    nonce += 1
    random_sleep(10, 45)

    # Отправляем депозит 2
    amount2 = generate_random_amount()
    print(f"Отправка второго депозита на {w3.from_wei(amount2, 'ether')} ETH...")
    tx_hash2 = send_deposit_transaction(amount2, nonce, private_key)
    print(f"{Fore.GREEN}✓ Второй депозит отправлен. Хэш: {tx_hash2.hex()}{Style.RESET_ALL}")
    nonce += 1
    random_sleep(10, 45)

    # Выполняем свап 3 раза
    for j in range(3):
        swap_amount = generate_random_amount()
        print(f"Отправка транзакции для свапа {j + 1} на {w3.from_wei(swap_amount, 'ether')} ETH...")
        tx_hash = send_swap_transaction(nonce, swap_amount, private_key)
        nonce += 1
        random_sleep(10, 45)

    # Отправляем токены 3 раза
    token_address = "0x03a519f1bd19ce974566ba91190b62d5c00e3a81"
    for k in range(3):
        eth_amount = random.uniform(0.01, 0.99)
        amount = w3.to_wei(eth_amount, 'ether')
        print(
            f"Отправка токенов на адрес {token_address} для транзакции {k + 1} на {eth_amount:.2f} ETH ({amount} wei)...")
        tx_hash = send_erc20_transaction(token_address, address, amount, nonce, private_key)
        nonce += 1
        random_sleep(10, 45)

    # Выполняем withdrawAndClaim
    withdraw_amount = generate_random_amount()
    print(f"Отправка транзакции для withdrawAndClaim на {w3.from_wei(withdraw_amount, 'ether')} ETH...")
    tx_hash = send_withdraw_and_claim_transaction(withdraw_amount, nonce, private_key)
    if tx_hash:
        nonce += 1

    # Выполняем клейм 2 раза
    for _ in range(2):
        print(f"Отправка транзакции для claim...")
        tx_hash = send_claim_transaction(nonce, private_key)
        if tx_hash:
            nonce += 1
        random_sleep(10, 45)

    # Пауза между аккаунтами
    random_sleep(30, 60)