import threading
from copy import deepcopy
from datetime import timezone,datetime
import random


from flask import Flask, request,jsonify
import datetime
import re
from wallet import Wallet
import socket
from block import Block,BlockChain,Input,Output,Transaction
import json

import time
import requests
from typing import Dict, List, Callable

# 路由节点
class Router:
    def __init__(self,own_port: int):
        self.own_port = own_port
        self.address_pool: Dict[str, float] = {"127.0.0.1:8333":time.time()}  # 地址池，键为地址（ip:port形式），值为对应的时间戳
        self.app = Flask(__name__)

        # 获取自身IP地址 , 这里初始化为 127.0.0.1
        self.own_ip = "127.0.0.1"
        self.hook_before_run:List[Callable] = [self.addr,self.getaddr]
        self.app.add_url_rule('/addr', methods=['POST'], view_func=self.addr_handler)
        self.app.add_url_rule('/getaddr', methods=['GET'], view_func=self.getaddr_handler)
        self.app.add_url_rule('/heartbeat', methods=['GET'], view_func=self.heartbeat_handler)
        if self.own_port == 8333:
            del self.address_pool["127.0.0.1:8333"]
    def add_routes(self,rule:str,methods:List[str],view_func:Callable):
        self.app.add_url_rule(rule,methods=methods,view_func=view_func)

    def addr_handler(self):
        """处理别人的POST请求"""
        data = request.get_json()
        other_address = data.get('address')
        if other_address:
            # 验证接收到的地址是否符合ip:port格式
            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$', other_address):
                self.address_pool[other_address] = time.time()
                return jsonify({"code":200,"message": "Address received successfully"}), 200
            return jsonify({"code":400,"message": "Invalid address format"}), 400
        return jsonify({"code":400,"message": "Invalid address data"}), 400

    def getaddr_handler(self):
        """处理获取邻居节点地址的GET请求"""
        return jsonify(self.address_pool),200

    def heartbeat_handler(self):
        # 返回 200
        return jsonify({"code":200,"message": f"{self.own_ip}:{self.own_port} alive"}),200

    def addr(self) -> None:
        """
        广播自己的地址（包括IP和端口号）给其他节点

        :param own_ip: 自身的IP地址
        """
        own_address = f"{self.own_ip}:{self.own_port}"
        for address, _ in self.address_pool.items():
            try:
                if address == own_address:
                    continue
                requests.post(f"http://{address}/addr", json={'address': own_address})
            except requests.exceptions.RequestException:
                print("error:addr")
                pass

    def getaddr(self) -> Dict[str, float]:
        """
        向地址池中的每个地址发送GET请求获取邻居节点的地址信息，并处理返回的数据

        :return: 合并后的所有有效地址信息字典，键为地址（ip:port形式），值为对应的时间戳
        """
        own_address = f"{self.own_ip}:{self.own_port}"
        all_addresses = {}
        for address, _ in self.address_pool.items():
            if own_address == address:
                continue
            try:
                response = requests.get(f"http://{address}/getaddr")
                if response.status_code == 200:
                    addresses_data = response.json()
                    for addr, timestamp in addresses_data.items():
                        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$', addr):
                            all_addresses[addr] = timestamp
            except requests.exceptions.RequestException:
                print("error:getaddr")
                pass
        self.address_pool.update(all_addresses)
        print(self.own_port,":",all_addresses)
        return all_addresses

    def send_heartbeat(self) -> None:
        """
        每过1秒向地址池中的每个地址发送心跳检测包，并根据响应更新地址池
        """
        current_time = time.time()
        addresses_to_remove = []

        for address, last_heartbeat_time in self.address_pool.items():
            try:
                # 假设其他节点有一个接收心跳检测包的接口，例如 /heartbeat
                response = requests.get(f"http://{address}/heartbeat")
                if response.status_code == 200:
                    self.refresh_address_time(address)
            except requests.exceptions.RequestException:
                addresses_to_remove.append(address)

        for address in addresses_to_remove:
            del self.address_pool[address]

    def refresh_address_time(self, address: str) -> None:
        """
        刷新指定地址对应的时间

        :param address: 要刷新时间的地址（ip:port形式）
        """
        self.address_pool[address] = time.time()

    def run(self):
        """启动Flask应用"""
        for hook in self.hook_before_run:
            hook()
        # 启动心跳检测线程
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        heartbeat_thread.start()
        self.app.run(port=self.own_port)

    def _heartbeat_loop(self):
        while True:
            # self.send_heartbeat()
            time.sleep(60) # 30 s 发送一次心跳请求

# 矿工节点类
class MinerNode(Router):
    def __init__(self, own_port:int,blockchain_file: str):
        super().__init__(own_port)
        self.transaction_list:List[Transaction] = []            # 临时的保存的交易池
        self.orphan_blocks:List[Block] = []                     # 孤儿交易池
        self.blockchain:BlockChain = BlockChain.read_blockchain(blockchain_file) # 本矿工节点的区块链
        self.add_routes('/addBlock',methods=['POST'], view_func=self.addBlock_handler)
        self.add_routes('/getBlockChain',methods=['GET'],view_func=self.getBlockChain_handler)
        self.add_routes('/post_transaction',methods=['POST'],view_func=self.post_transaction_handle)
        threading.Thread(target = self._pack_block).start() # 负责观察 transaction_list 并打包

    def post_transaction_handle(self):
        response = request.get_json() # 接收一个交易的序列化
        transaction_data = response['transaction']
        assert (isinstance(transaction_data, dict))
        transact = Transaction.from_dict(transaction_data)
        transact.verify(self.blockchain)               # 进行验证
        self.transaction_list.append(transact)
        return {"code":200,"message":"Transaction received successfully"}

    def addBlock_handler(self):
        response = request.get_json() # 接收一个区块的序列化
        block_data = response['block']
        assert(isinstance(block_data,dict))
        block = Block.from_dict(block_data)

        # 清理一下已经被别人打包的交易
        filtered_transactions = [tx for tx in self.transaction_list if not block.is_transaction_in(tx.Hash)]
        self.transaction_list = filtered_transactions


        if not self.blockchain.add_block(block):
            # 如果是孤儿节点，则加入到孤儿池中，等待父节点被添加后，再尝试添加
            self.orphan_blocks.append(block)
            print("orphan block")
            print("current_hash: ",self.blockchain.current_hash," block_hash: ",block.Hash)
            return jsonify({"code":400,"message":"Orphan block."}),400
        # 查看孤儿池中是否有子节点可以添加
        self._orphan_block_to_blockchain(block.Hash)
        self._save()
        return jsonify({"code":200,"message":"Block added."}),200

    def getBlockChain_handler(self):
        '''

        :return: 返回对方没有的 Block
        '''
        # 从GET请求的参数中获取datetime参数
        datetime_str = request.args.get('datetime')
        timestamp = datetime.datetime.fromisoformat(datetime_str)
        return json.dumps([block.to_dict()
                           for block in self.blockchain.get_blocks_after_time(timestamp)]),200

    def addBlock(self):
        '''把最新的 block 传播出去'''
        own_address = f"{self.own_ip}:{self.own_port}"
        for address in self.address_pool.keys():
            if own_address == address:
                continue
            block = self.blockchain[-1]
            response = requests.post(f"http://{address}/addBlock", json={'block': block.to_dict()})
            print(address," ",response.status_code)
            # print(address)

    def _pack_block(self):
        while True:
            '''TODO 挖矿逻辑可以在这里补充'''
            time.sleep(random.randint(1,10))
            if len(self.transaction_list) == 0:
                continue

            block = Block(
                Timestamp=datetime.datetime.now(timezone.utc),
                Transactions=deepcopy(self.transaction_list),
                PrevBlockHash=deepcopy(self.blockchain.current_hash),
                Hash="",
                Nonce=0,                               # 和挖矿相关的字段
                Height=self.blockchain.height,         # 和当前节点相关
                Difficulty=4                           # 当前无用
            )
            block.set_hash()
            assert(len(block.Transactions)!=0)
            self.blockchain.add_block(block)
            self.addBlock()             # 广播出去
            self.transaction_list.clear()
            self._save()

    def _save(self):
        '''
        模拟保存区块链
        :return:
        '''
        addr = f"./data/{self.own_ip}_{self.own_port}.json"
        self.blockchain.save_blockchain(addr)

    def _orphan_block_to_blockchain(self, father_block_hash:str):
        """将孤儿池中的父节点为 father_block_hash 的区块添加到区块链中"""
        if father_block_hash == "":
            return
        orphan_block_hash = ""
        for orphan_block in self.orphan_blocks:
            if orphan_block.PrevBlockHash == father_block_hash:
                self.blockchain.add_block(orphan_block)
                print("orphan block added")
                orphan_block_hash = orphan_block.Hash
                self.orphan_blocks.remove(orphan_block)
                break
        # 孤儿池中可能还有其他孤儿，需要继续遍历
        return self._orphan_block_to_blockchain(orphan_block_hash)



if __name__ == '__main__':
    # 单独启动一个 router
    router = MinerNode(8333,'./data/bb.json')
    threading.Thread(target=router.run).start()
    time.sleep(1)
    port_list = [8334,8335,8336,8337]
    router_list = []
    for port in port_list:
        router_list.append(MinerNode(port,'./data/bb.json'))
    # 创建线程列表
    thread_list = []

    for router in router_list:
        # 为每个Router实例创建一个线程
        thread = threading.Thread(target=router.run)
        thread_list.append(thread)
        # 启动线程
        thread.start()

    #time.sleep(10)
    for thread in thread_list:
        thread.join()
