
import ecdsa
import hashlib
import json
import base58
from dataclasses import dataclass,field

import json
import os
from dataclasses import dataclass
from ecdsa import SigningKey, SECP256k1
from base58 import b58encode_check
from hashlib import sha256, new as new_hash



@dataclass
class Wallet:
    pub_key: str = None
    private_key: str = None
    address: str = None

    def new_address(self):
        # 生成私钥
        private_key = SigningKey.generate(curve=SECP256k1)
        self.private_key = private_key.to_string().hex()

        # 从私钥获取公钥
        public_key = private_key.get_verifying_key()
        self.pub_key = public_key.to_string().hex()

        # 公钥生成比特币地址的完整过程，包含多次哈希操作
        public_key_bytes = bytes.fromhex(self.pub_key)

        # 第一次哈希（SHA256）
        sha256_hash = sha256(public_key_bytes).digest()

        # 第二次哈希（RIPEMD160）
        ripemd160 = new_hash('ripemd160')
        ripemd160.update(sha256_hash)
        hash160 = ripemd160.digest()

        # 添加版本字节（比特币主网版本字节为0x00）
        versioned_hash = b'\x00' + hash160

        # 进行两次哈希（SHA256）操作以获取校验和
        first_sha256 = sha256(versioned_hash).digest()
        second_sha256 = sha256(first_sha256).digest()

        # 取前4个字节作为校验和
        checksum = second_sha256[:4]

        # 组合版本字节、哈希结果和校验和
        address_bytes = versioned_hash + checksum

        # 进行Base58编码得到最终的比特币地址
        self.address = b58encode_check(address_bytes).decode()

        return self.address

    def load_from_file(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                wallet_data = json.load(f)
                self.pub_key = wallet_data.get('pub_key')
                self.private_key = wallet_data.get('private_key')
                self.address = wallet_data.get('address')
        else:
            print(f"文件 {file_path} 不存在。")

    def save_to_file(self, file_path):
        wallet_data = {
            'pub_key': self.pub_key,
            'private_key': self.private_key,
            'address': self.address,
        }
        with open(file_path, 'w') as f:
            json.dump(wallet_data, f)


if __name__ == '__main__':
    def generate_mnemonic_wallet():
        wallet = Wallet()
        wallet.new_address()
        return wallet

    # 示例用法：生成新钱包并保存到文件
    wallet = generate_mnemonic_wallet()
    print(f"地址: {wallet.address}")
    wallet.save_to_file('wallet.json')
    # 示例用法：从文件加载钱包
    loaded_wallet = Wallet()
    loaded_wallet.load_from_file('wallet.json')
    print(f"加载的地址: {loaded_wallet.address}")

