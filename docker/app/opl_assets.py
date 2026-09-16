"""OPL 2026 optional training assets. All proxy dimensions/masses are project defaults."""
import math

REVISION = 'd893b1db7432565a054be0da7ce09a2495425c5e'
SOURCE = 'https://github.com/RoboCupAtHomeJP/AtHome2026/blob/' + REVISION
# Each row is the PDF ID, its published name, and an existing YCB key.
YCB_ROWS = [
 (1,'Tomato soup can','005_tomato_soup_can'),(2,'Spam','010_potted_meat_can'),
 (10,'Apple','013_apple'),(11,'Lemon','014_lemon'),(12,'Peach','015_peach'),
 (13,'Orange','017_orange'),(14,'Strawberry','012_strawberry'),
 (15,'Fork','030_fork'),(16,'Knife','032_knife'),(17,'Spoon','031_spoon'),
 (18,'Plate','029_plate'),(19,'Bowl','024_bowl'),(20,'Mug','025_mug'),
 (22,'Sponge','026_sponge'),(24,'Rubik cube (solved)','077_rubiks_cube')]
CATALOG = [dict(row=i,label=n,key='ycb_'+k,kind='既存YCB（凸分解近似）') for i,n,k in YCB_ROWS]
PROXIES = {}
FURNITURE = {}

def box(size,pos=(0,0,0),color=(.55,.38,.22,1)):
    return dict(type='box',size=[v/2 for v in size],pos=list(pos),rgba=list(color))

def hollow(size,wall=.005,color=(.3,.6,.3,1)):
    x,y,z=size
    return [box((x,y,wall),(0,0,-z/2+wall/2),color),
            box((wall,y,z),(-x/2+wall/2,0,0),color),
            box((wall,y,z),(x/2-wall/2,0,0),color),
            box((x-2*wall,wall,z),(0,-y/2+wall/2,0),color),
            box((x-2*wall,wall,z),(0,y/2-wall/2,0),color)]

def cup(radius,height,color):
    # Upright, open interior: cylinder floor plus 20 box wall segments.
    wall=.003
    result=[dict(type='cylinder',size=[radius,wall/2],pos=[0,0,-height/2+wall/2],rgba=list(color))]
    # Axis-aligned small boxes around a ring avoid adding primitive rotations.
    for i in range(32):
        a=2*math.pi*i/32
        result.append(box((.012,.012,height),( (radius-.006)*math.cos(a),
                         (radius-.006)*math.sin(a),0),color))
    return result

def proxy(row,key,label,size,mass,shape='box',color=(.6,.65,.75,1)):
    geoms=[box(size,color=color)]
    if shape=='cylinder':geoms=[dict(type='cylinder',size=[size[0]/2,size[2]/2],pos=[0,0,0],rgba=list(color))]
    if shape=='cup':geoms=cup(size[0]/2,size[2],color)
    if shape=='hollow':geoms=hollow(size,color=color)
    full='opl_'+key
    PROXIES[full]=dict(id='openarm_'+full,label=label+'（剛体近似）',size=list(size),
                      mass=mass,half_height=size[2]/2,geoms=geoms,opl=True)
    CATALOG.append(dict(row=row,key=full,label=label,kind='剛体近似・寸法/質量は既定値'))
    return full

proxy(25,'lemonade','Lemonade',(.065,.065,.22),.55,'cylinder',(.9,.8,.15,1))
proxy(26,'coffee_can','Coffee Can',(.053,.053,.105),.20,'cylinder',(.13,.12,.10,1))
proxy(27,'fanta','Fanta',(.068,.068,.22),.53,'cylinder',(.95,.4,.1,1))
proxy(28,'yakult','Yakult',(.04,.04,.09),.08,'cylinder',(.9,.8,.65,1))
proxy(29,'green_tea','Green Tea (heavy)',(.085,.085,.28),1.05,'cylinder',(.3,.55,.12,1))
proxy(30,'milk','Milk (liquid mass approximation)',(.07,.07,.235),1.03,'box',(.85,.9,1,1))
proxy(31,'red_bull','Red Bull can (empty)',(.053,.053,.135),.015,'cylinder',(.2,.3,.8,1))
proxy(32,'chocolate_snack','Chocolate Snack',(.16,.085,.035),.06,'box',(.2,.6,.12,1))
proxy(33,'jagarico','Jagarico',(.085,.085,.10),.065,'cup',(.6,.8,.2,1))
proxy(34,'gummy','Gummy',(.10,.025,.15),.08,'box',(.7,.25,.6,1))
proxy(35,'cereal','Cereal',(.16,.065,.24),.3,'box',(.3,.7,.3,1))
proxy(36,'cup_noodle','Cup Noodle',(.10,.10,.11),.09,'cup',(.9,.8,.6,1))
proxy(37,'cup_rice','Cup Rice',(.10,.10,.105),.11,'cup',(.85,.6,.3,1))
proxy(38,'dishwasher_tab','Dishwasher Tab (package)',(.10,.06,.14),.4,'box',(.2,.65,.9,1))
proxy(39,'toothpaste_box','Toothpaste box',(.045,.035,.18),.13,'box',(.35,.7,.8,1))
proxy(40,'bag','Bag (unspecified; rigid proxy)',(.25,.12,.30),.10,'hollow')
cloth=proxy(41,'clothes','Clothes (rigid folded piece 1/12)',(.20,.16,.015),.15,'box',(.4,.5,.8,1))
# One official row represents a set: expose 12 independently placeable rigid pieces.
import copy
for i in range(2,13):
    key='opl_clothes_'+str(i)
    PROXIES[key]=copy.deepcopy(PROXIES[cloth])
    PROXIES[key]['id']='openarm_'+key
    PROXIES[key]['label']='Clothes (rigid folded piece '+str(i)+'/12)'
    PROXIES[key]['geoms'][0]['rgba']=[.25+i*.035,.55,.8-i*.035,1]
proxy(42,'laundry_basket','Laundry Basket (TORKIS-like proxy)',(.50,.35,.25),.8,'hollow')
proxy(43,'tray','Tray',(.35,.25,.035),.25,'hollow',(.6,.4,.22,1))

def furniture(key,label,size,geoms,surfaces):
    key='opl_'+key
    FURNITURE[key]=dict(id='openarm_'+key,label=label+'（家具近似）',size=list(size),
        mass=20.,half_height=size[2]/2,geoms=geoms,furniture=True,surfaces=surfaces)
def surface(name,x,y,z,px=0,py=0):
    return dict(name=name,size=[x,y],position=[px,py,z])
def table(key,label,x,y,h):
    t=.04
    geoms=[box((x,y,t),(0,0,h/2-t/2))]
    geoms += [box((.045,.045,h-t),(sx*(x/2-.04),sy*(y/2-.04),-t/2))
              for sx in (-1,1) for sy in (-1,1)]
    furniture(key,label,(x,y,h),geoms,[surface('top',x,y,h/2)])
table('side_table','Side Table',.50,.50,.55)
table('dining_table','Dining Table',1.20,.75,.72)
table('table','Table',1.0,.65,.70)
table('coffee_table','Coffee Table',.90,.50,.40)

def shelf(key,label,x,y,h,levels):
    t=.025
    geoms=[box((t,y,h),(-x/2+t/2,0,0)),box((t,y,h),(x/2-t/2,0,0)),
           box((x,t,h),(0,y/2-t/2,0))]
    surfaces=[]
    for i,z in enumerate(levels):
        geoms.append(box((x-2*t,y,t),(0,0,z-h/2-t/2)))
        surfaces.append(surface('shelf'+str(i+1),x-2*t,y-t,z-h/2,py=-t/2))
    furniture(key,label,(x,y,h),geoms,surfaces)
shelf('bookcase','Bookcase',.70,.32,1.50,[.12,.55,1.0,1.50])
shelf('cabinet','Cabinet',.80,.40,.90,[.12,.50,.90])
for key,label,x,y,h in [('dishwasher','Dishwasher',.60,.60,.85),('washing_machine','Washing Machine',.60,.60,.85),('microwave','Microwave',.50,.38,.30)]:
    # Open-front box, fixed rack: no doors, actuator, heat or water simulation.
    shelf(key,label,x,y,h,[.035,h])
furniture('trash_bin','Trash Bin',(.32,.32,.50),hollow((.32,.32,.50),.015),
          [surface('inside',.29,.29,-.235)])
furniture('bed','Bed',(1.9,.90,.45),[box((1.9,.90,.45))],[surface('top',1.9,.90,.225)])
furniture('couch','Couch',(1.5,.75,.80),
          [box((1.5,.75,.38),(0,0,-.21)),box((1.5,.12,.42),(0,.315,.19)),
           box((.12,.63,.30),(-.69,-.06,.13)),box((.12,.63,.30),(.69,-.06,.13))],
          [surface('seat',1.26,.63,-.02,py=-.06)])
furniture('chair','Chair',(.45,.48,.85),
          [box((.45,.48,.04),(0,0,.005)),box((.45,.04,.40),(0,.22,.225))]+
          [box((.04,.04,.40),(x,y,-.225)) for x in (-.19,.19) for y in (-.20,.20)],
          [surface('seat',.45,.44,.025,py=-.02)])
furniture('coat_rack','Coat rack',(.55,.55,1.65),
          [box((.55,.55,.04),(0,0,-.805)),box((.04,.04,1.61),(0,0,.02)),
           box((.50,.04,.04),(0,0,.65)),box((.04,.50,.04),(0,0,.55))],[])
SURFACE_IDS=['worktable']+[k+':'+s['name'] for k,o in FURNITURE.items() for s in o['surfaces']]
