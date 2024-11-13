import threading

from flask import Flask, request,jsonify
import datetime
import re
from block import BlockChain,Transaction,Block
from wallet import Wallet
import socket
from block import Block,BlockChain,Input,Output
import json

import time
import requests
from typing import Dict, List, Callable


class Router:
    def __init__(self,own_port: int):
        self.own_port = own_port
        self.address_pool: Dict[str, float] = {"127.0.0.1:8333":time.time()}  # 地址池，键为地址（ip:port形式），值为对应的时间戳
        self.app = Flask(__name__)

        # 获取自身IP地址
        self.own_ip = "127.0.0.1"
        self.hook_before_run:List[Callable] = [self.addr,self.getaddr]
        self.app.add_url_rule('/addr', methods=['POST'], view_func=self.addr_handler)
        self.app.add_url_rule('/getaddr', methods=['GET'], view_func=self.getaddr_handler)
        self.app.add_url_rule('/heartbeat', methods=['GET'], view_func=self.heartbeat_handler)

    def add_routes(self,rule:str,methods:List[str],view_func:Callable):
        self.app.add_url_rule(rule,methods=methods,view_func=view_func)

    def addr_handler(self):
        """处理别人的POST请求"""
        data = request.get_json()
        other_address = data.get('address')
        print("addr_handler",other_address)
        if other_address:
            # 验证接收到的地址是否符合ip:port格式
            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$', other_address):
                self.address_pool[other_address] = time.time()
                return jsonify({"message": "Address received successfully"}), 200
            return jsonify({"message": "Invalid address format"}), 400
        return jsonify({"message": "Invalid address data"}), 400

    def getaddr_handler(self):
        """处理获取邻居节点地址的GET请求"""
        return jsonify(self.address_pool)

    def heartbeat_handler(self):
        # 返回 200
        return ""

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
                print(address)
                print(own_address)
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
            self.send_heartbeat()
            time.sleep(30) # 30 s 发送一次心跳请求

# 矿工节点类
class MinerNode(Router):
    def __init__(self, own_port:int,blockchain_file: str):
        super().__init__(own_port)
        self.transaction_list:List[Transaction] = []            # 临时的保存的交易池
        self.blockchain:BlockChain = BlockChain.read_blockchain(blockchain_file) # 本矿工节点的区块链
        self.add_routes('/addBlock',methods=['POST'], view_func=self.addBlock_handler)


    def addBlock_handler(self):
        block_data = request.get_json()
        assert(isinstance(block_data, dict))
        block = Block.from_dict(block_data)
        self.blockchain.add_block(block)
        return "区块添加成功"

        @self.app.route('/getBlockChain', methods=['GET'])
        def getBlockChain():
            return json.dumps(self.blockchain.to_dict())



if __name__ == '__main__':
    # 单独启动一个 router
    router = Router(8333)
    threading.Thread(target=router.run).start()
    time.sleep(1)
    port_list = [8334,8335]
    router_list = []
    for port in port_list:
        router_list.append(Router(port))

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