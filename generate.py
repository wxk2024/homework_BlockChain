
from wallet import Wallet
from block import Transaction,Input,Output,Block
import requests
import time

if __name__ == '__main__':
    wallet_a = Wallet()
    wallet_a.load_from_file("./data/wallet_a.json")

    wallets = [Wallet().new_address() for i in range(5)]

    address_list = ['127.0.0.1:8333',
                 '127.0.0.1:8334',
                 '127.0.0.1:8335',
                 '127.0.0.1:8336',
                 '127.0.0.1:8337']
    k = 0
    for i in range(5):
        # 5 个地址
        transfer_transaction = Transaction(
            Hash="",  # 该交易需要验证通过后，再计算 Hash 等待上链
            Vin=[Input(
                txid="",  # 使用创世区块的那笔交易
                vout=0,
                signature="",  # 等待 A 进行签名
                pubkey=wallet_a.pub_key  # A 需要花钱，因此 使用 A 的公钥来证明所属
            )],
            Vout=[Output(value=5, pubkey=wallets[i].pub_key),  # 给 对方 转钱
                  Output(value=95, pubkey=wallet_a.pub_key)]  # 给 A 自己转钱
        )
        transfer_transaction.sign(wallet_a.private_key)
        address = address_list[i]
        for j in range(5):
            # 每个地址 5 笔交易
            response = requests.post(f"http://{address}/post_transaction", json={"transaction":transfer_transaction.to_dict()})
            print(response.text)
            k+=1
        time.sleep(10)

    print("finished: ", k)