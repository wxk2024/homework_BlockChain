from datetime import datetime,timezone
from typing import List
import hashlib
import json
import string
import random
import ecdsa
from typing import Dict
from ecdsa import SigningKey, VerifyingKey, SECP256k1
from dataclasses import dataclass, field
from wallet import Wallet

def generate_random_string(length: int) -> str:
    """生成指定长度的随机字符串"""
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))

@dataclass
class Input:
    txid: str = field(metadata={'description': '交易哈希，用于唯一标识一笔交易'})
    vout: int = field(metadata={'description': '交易中输出序号，指定该交易的哪个输出被引用作为输入'})
    signature: str = field(metadata={'description': '支付方的签名，对交易进行签名的数据，用于验证交易的合法性'})
    pubkey: str = field(metadata={'description': '接收方的公钥,与私钥对应的公钥，用于验证签名'})

    def to_dict(self) -> dict:
        return {
            'txid': self.txid,
            'vout': self.vout,
            'signature': self.signature,
            'pubkey': self.pubkey
        }

@dataclass
class Output:
    value: float = field(metadata={'description': '交易输出的金额数值'})
    pubkey: str = field(metadata={'description': '接收该交易输出金额的公钥'})
    def to_dict(self) -> dict:
        return {
            'value': self.value,
            'pubkey': self.pubkey
        }


@dataclass
class Transaction:
    Version:int = field(init=False,default=1)  # 默认就是 v1
    Hash: str                                  # 验证成功后使用 hash 函数进行设置
    Vin: List[Input]
    Vout: List[Output]

    def __post_init__(self):
        if len(self.Vout) <= 0 :
            raise Exception("len(Vout) <= 0")

    def verify(self,bc):
        """
        1.检查 vin 是否在区块中
        2.检查余额是否足够
        3.Pay-to-Public-Key P2PK 进行身份验证
        :return:
        """
        # 检查vin是否在区块中（这里假设可以通过某种方式查询区块数据，暂未实现具体逻辑）
        usable_money = 0
        for input_obj in self.Vin:
            # 假设这里有一个函数可以检查输入是否在区块中，比如 check_input_in_block(input_obj.txid, input_obj.vout)
            is_in_block,num_money = self._check_input_in_block(input_obj.txid, input_obj.vout,bc)
            if not is_in_block:
                raise Exception("vin 不在区块中")
            usable_money+=num_money

            # 验证钱是不是你的
            # 验证输入交易的签名是否有效
            if not self.verify_input_signature(input_obj):
                raise Exception("钱不是你的")
        expend_money = 0
        for output_obj in self.Vout:
            expend_money += output_obj.value
        if usable_money < expend_money:
            raise Exception("花的钱太多了")
        # 验证通过后，进行求hash
        self._set_hash()
    def sign(self, priv_key):
        signing_key = SigningKey.from_string(bytes.fromhex(priv_key), curve=SECP256k1)
        for input_obj in self.Vin:
            message = f"{input_obj.txid}{input_obj.vout}".encode()
            signature = signing_key.sign(message)
            input_obj.signature = signature.hex()   # A 对交易进行了签名，接下来就需要验证

    def _set_hash(self)->None:
        self.Hash = self.hash()
    def hash(self)->str:
        transaction_data = {
            "Vin": [{"txid": input_obj.txid, "vout": input_obj.vout,
                     "signature": input_obj.signature, "pubkey": input_obj.pubkey}
                    for input_obj in self.Vin],
            "Vout": [{"value": output_obj.value, "pubkey": output_obj.pubkey} for output_obj in self.Vout]
        }
        json_data = json.dumps(transaction_data)
        self.Hash = hashlib.sha256(json_data.encode()).hexdigest()
        return self.Hash

    def _check_input_in_block(self, txid:str, vout:int, bc)->(bool, int):
        """
        检查来源是否在区块中，并返回钱的数量

        :param txid: 哪一笔交易
        :param vout: 交易中那一笔输出
        :return: (bool,int) : 是否在区块中，钱是多少
        """

        for block in bc.blocks:
            for transaction in block.Transactions:
                if transaction.Hash == txid and len(transaction.Vout)>vout:
                    usable_money = transaction.Vout[vout].value
                    return True, usable_money

        return False,0
    def verify_input_signature(self,input_obj):
        verifying_key = ecdsa.VerifyingKey.from_string(bytes.fromhex(input_obj.pubkey), curve=ecdsa.SECP256k1)
        message = f"{input_obj.txid}{input_obj.vout}".encode()
        try:
            return verifying_key.verify(bytes.fromhex(input_obj.signature), message)
        except ecdsa.BadSignatureError:
            return False
    def to_dict(self)->Dict:
        return {
            "Hash": self.Hash,
            "Vin":[i.to_dict() for i in self.Vin],
            "Vout":[o.to_dict() for o in self.Vout]
        }
    @staticmethod
    def from_dict(t: Dict) -> 'Transaction':
        vin: List[Input] = [Input(**input_data) for input_data in t['Vin']]
        vout: List[Output] = [Output(**output_data) for output_data in t['Vout']]
        transaction = Transaction(Hash=t['Hash'], Vin=vin, Vout=vout)
        return transaction

@dataclass
class Block:
    Timestamp: datetime
    Transactions: List[Transaction]
    PrevBlockHash: str
    Hash: str
    Nonce: int
    Height: int
    Difficulty: int = field(default=4)  # 添加难度字段，默认为4，可根据需要调整

    @staticmethod
    def new_block(transactions:List[Transaction], prev_hash:str, height:int,difficulty:int)->'Block':
        '''
        创建新区块，同时调用 set_hash 获取自己的哈希值

        :param prev_hash:
        :param height:
        :param transactions: 该区块中包含的 transactions 交易数据
        :param difficulty:
        :return: Block
        '''
        timestamp = datetime.now(timezone.utc)
        return Block(timestamp, transactions, prev_hash, "",0,height,difficulty)
    def set_hash(self)->str:
        '''
        计算当前hash值
        计算方法如下：将block的Timestamp和PrevBlockHash链接成字符串，对其使用sha256函数取哈希值
        :return:
        '''
        header_bin = (str(self.Timestamp) + str(self.PrevBlockHash)).encode()
        inner_hash = hashlib.sha256(header_bin).hexdigest().encode()
        outer_hash = hashlib.sha256(inner_hash).hexdigest()
        self.Hash = outer_hash
        return outer_hash
    def to_dict(self):
        return {
            'Timestamp': self.Timestamp.isoformat(),
            'Transactions': [t.to_dict() for t in self.Transactions],
            'PrevBlockHash': self.PrevBlockHash,
            'Hash': self.Hash,
            'Nonce': self.Nonce,
            'Height': self.Height,
            'Difficulty': self.Difficulty
        }
    @staticmethod
    def from_dict(b:Dict)->'Block':
        transactions = []
        for t in b['Transactions']:
            vin: List[Input] = [Input(**input_data) for input_data in t['Vin']]
            vout: List[Output] = [Output(**output_data) for output_data in t['Vout']]
            transaction = Transaction(Hash=t['Hash'], Vin=vin, Vout=vout)
            transactions.append(transaction)

        block = Block(
            Timestamp=datetime.fromisoformat(b['Timestamp']),
            Transactions=transactions,
            PrevBlockHash=b['PrevBlockHash'],
            Height=b['Height'],
            Difficulty=b['Difficulty'],
            Hash=b['Hash'],
            Nonce=b['Nonce']
        )
        return block

@dataclass
class BlockChain:
    def __init__(self,blocks:List[Block]=[],current_hash:str="",height:int=0):
        self.blocks:List[Block] = blocks
        self.current_hash:str = current_hash  # 最新区块的哈希值
        self.height:int = height         # 区块链的高度

    def __getitem__(self, index):
        return self.blocks[index]
    def __len__(self):
        return self.height
    def add_block(self,block:Block):
        '''
        添加区块，传入一个block对象，加入blocks数组并更新current_hash和height
        :return:
        '''
        assert(block.Hash is not None)
        assert(block.PrevBlockHash == self.current_hash) # self.blocks 中至少有一个
        assert(len(block.Transactions)!=0)
        self.blocks.append(block)
        self.current_hash = block.Hash
        self.height += 1
        pass
    def get_block(self,block_hash:str)->Block:
        '''
        通过 block 的 hash 值来查找区块，返回一个block对象
        :param block_hash:
        :return:
        '''
        for block in self.blocks:
            if block.Hash == block_hash:
                return block
        return None
    def to_dict(self)->Dict:
        blocks_data = [block.to_dict() for block in self.blocks]
        blockchain_data = {
            'blockchain': [{'block': block_data} for block_data in blocks_data]
        }
        return blockchain_data
    def save_blockchain(self, file_path: str) -> None:
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)
    def get_blocks_after_time(self,timestamp:datetime)->List[Block]:
        res = []
        for block in self.blocks[::-1]:
            if block.Timestamp > timestamp:
                res.insert(0, block)
        return res
    def get_last_block_hash(self):
        return self.current_hash
    @staticmethod
    def read_blockchain(file_path: str) -> 'BlockChain':
        with open(file_path, 'r') as f:
            blockchain_data = json.load(f)
            blocks_data = [list(block.values())[0] for block in blockchain_data['blockchain']]

            blocks = []
            for b in blocks_data:
                block = Block.from_dict(b)
                blocks.append(block)
            current_hash = blocks[-1].Hash if blocks else None
            height = len(blocks)
            return BlockChain(blocks,current_hash,height)

if __name__ == '__main__':
    # 创建钱包A并生成地址
    wallet_a = Wallet()
    wallet_a.new_address()
    wallet_a.save_to_file("wallet_a.json")

    # 创建钱包B并生成地址
    wallet_b = Wallet()
    wallet_b.new_address()
    wallet_b.save_to_file("wallet_b.json")
    # 创建给钱包A转账的交易（创世交易）
    genesis_transaction = Transaction(
        Hash="",
        Vin=[],
        Vout=[Output(value=100, pubkey=wallet_a.pub_key)]
    )
    # 创世交易不需要验证
    # 创建创世区块并添加创世交易
    genesis_block = Block(
        Timestamp=datetime.now(timezone.utc),
        Transactions=[genesis_transaction],
        PrevBlockHash="0000000000000000000000000000000000000000000000000000000000000000",
        Hash="",
        Nonce=0,
        Height=0
    )
    genesis_block.set_hash()

    # 创建区块链并添加创世区块
    blockchain = BlockChain()
    blockchain.add_block(genesis_block)
    blockchain.save_blockchain("blockchain_data.json")

    # 创建从钱包A向钱包B转账5个比特币的交易
    transfer_transaction = Transaction(
        Hash="",            # 该交易需要验证通过后，再计算 Hash 等待上链
        Vin=[Input(
            txid=genesis_transaction.Hash,  # 使用创世区块的那笔交易
            vout=0,
            signature="",                   # 等待 A 进行签名
            pubkey=wallet_a.pub_key  # A 需要花钱，因此 使用 A 的公钥
        )],
        Vout=[Output(value=5, pubkey=wallet_b.pub_key),  # 给 B 转钱
              Output(value=95, pubkey=wallet_a.pub_key)] # 给 A 自己转钱
    )
    transfer_transaction.sign(wallet_a.private_key)
    transfer_transaction.verify()
    transfer_transaction.set_hash()

    # 创建新区块并添加转账交易
    transfer_block = Block(
        Timestamp=datetime.now(timezone.utc),
        Transactions=[transfer_transaction],
        PrevBlockHash=genesis_block.Hash,
        Height=1,
        Hash="",
        Nonce=0
    )
    transfer_block.set_hash()
    blockchain.add_block(transfer_block)

    # 保存区块链到文件（这里只是示例，实际应用中文件路径等可根据需求调整）
    blockchain.save_blockchain("blockchain_data.json")

    bb = BlockChain.read_blockchain("blockchain_data.json")
    bb.save_blockchain("bb.json")




