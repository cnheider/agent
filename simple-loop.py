import neodroid as neo
from neodroid.messaging import Reaction
from neodroid.models import Motion
import time

env = neo.NeodroidEnvironment(name='dodgescene.exe',connect_to_running=True)

while(1):
  print('step')
  env.step(Reaction(False,[]))#[Motion('Player','Wheel1Torque',5.)]))
  #time.sleep(1)