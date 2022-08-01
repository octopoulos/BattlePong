# coding: utf-8
# @author octopoulo <polluxyz@gmail.com>
# @version 2022-07-31

"""
Pong server
"""

from math import sqrt
import signal
from time import time

import pyuv

from pong_common import *


class PongServer(Pong):
	def __init__(self, **kwargs):
		super(PongServer, self).__init__(**kwargs)
		print('PongServer', kwargs)

		self.connId  = 0
		self.id      = 0
		self.players = {}
		self.running = True
		self.server  = None                                      # type: pyuv.TCP
		self.slots   = [None, None, None, None]

		self.loop     = pyuv.Loop.default_loop()
		self.signal_h = pyuv.Signal(self.loop)

	# HELPERS
	#########

	def AddPlayer(self, client: pyuv.TCP, wantSlot: int) -> int:
		ip, port = client.getpeername()
		slot     = self.FindSlot(wantSlot)
		if slot < len(self.slots): self.slots[slot] = client
		self.players[client] = [slot, ip, port, 0, 0, 0]
		print('AddPlayer: players=')
		self.PrintPlayers()
		return slot

	def DeletePlayer(self, client: pyuv.TCP):
		if player := self.players.get(client):
			self.slots[player[0]] = None
			del self.players[client]
			print('DeletePlayer: players=')
			self.PrintPlayers()

	def FindSlot(self, wantSlot: int) -> int:
		numSlot = len(self.slots)
		if 0 <= wantSlot <= numSlot and not self.slots[wantSlot]: return wantSlot

		for i, slot in enumerate(self.slots):
			if not slot: return i
		# spectator
		return numSlot

	def PrintPlayers(self):
		print(self.slots)
		for key, value in self.players.items():
			print(' ', key, value)

	# NETWORK
	#########

	def OnConnect(self, server: pyuv.TCP, error: int):
		self.connId += 1
		client = pyuv.TCP(self.loop)
		self.server.accept(client)
		client.start_read(self.OnRead)

	def OnRead(self, client: pyuv.TCP, data: bytes, error: int):
		if data is None:
			client.close()
			self.DeletePlayer(client)
			return

		player  = self.players.get(client)
		pid     = player[0] if player else -1
		hasHttp = 0

		for line in data.decode().split('\r\n'):
			if not line:
				if hasHttp: hasHttp += 1
				continue
			elif hasHttp and hasHttp < 3:
				continue

			# 1) game
			# paddle
			if line[0] == 'P':
				items = line[1:].split(':')
				if 0 <= pid <= 3 and len(items) > 1 and DefaultInt(items[0], -1) == pid:
					self.paddles[pid].Parse(items)

					for sid, slot in enumerate(self.slots):
						if sid != pid and slot:
							self.Send(slot, f'{line}\r\n')

			# 2) connection
			elif line[0] == 'I':
				wantSlot = DefaultInt(line[1:], -1)
				if pid < 0: pid = self.AddPlayer(client, wantSlot)
				self.Send(client, f'I{pid}\r\n')
				for ball in self.balls:
					self.Send(client, ball.Format())

			# 3) http
			elif line[0: 5] == 'GET /':
				hasHttp = 1
				speed   = self.balls[0].body.linearVelocity

				html = ''.join([
					'<html>',
					'<body>',
						'<h1>Battle Pong</h1>',
						f'<div>Balls: {len(self.balls)}</div>',
						f'<div>Players: {len(self.players)}</div>',
						f'<div>Speed: {sqrt(speed[0] * speed[1] + speed[1] * speed[1])}</div>',
					'</body>',
					'</html>',
				])

				response = '\r\n'.join([
					'HTTP/1.1 200 OK',
					'Date: Sun, 18 Oct 2012 10:36:20 GMT',
					'Server: Custom/1.0.0',
					f'Content-Length: {len(html) + 4}',
					'Content-Type: text/html; charset=UTF-8',
					'',
					html,
					'<html><body><h1>Hello there!</h1></body></html>',
					'',
					'',
				])
				self.Send(client, response)
				self.DeletePlayer(client)
			else:
				print(f'player_{pid}:', line)

	def Signal(self, handle: pyuv.Signal, signum: int):
		for client in self.players:
			try:
				client.close()
			except:
				pass

		self.signal_h.close()
		self.server.close()
		self.running = False

	# GAME
	######

	def NewGame(self):
		super(PongServer, self).NewGame()

		for slot in self.slots:
			if slot:
				for ball in self.balls:
					if player := self.players.get(slot): player[0] = 1
					self.Send(slot, ball.Format())

	# MAIN LOOP
	###########

	def Run(self):
		self.server = pyuv.TCP(self.loop)
		self.server.bind((self.host, self.port))
		self.server.listen(self.OnConnect)
		self.connected = True

		self.signal_h.start(self.Signal, signal.SIGINT)

		self.NewGame()

		while self.running:
			self.PhysicsLoop()
			self.loop.run(pyuv.UV_RUN_NOWAIT)


def MainServer(**kwargs):
	print(f'Server: pyuv={pyuv.__version__}')
	server = PongServer(**kwargs)
	server.Run()
	print('Goodbye.')


if __name__ == '__main__':
	MainServer()
