import operator
import re
from http import HTTPStatus
import os

from flask import Flask, jsonify, request, abort

app = Flask(__name__)

variable_re = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

robots = {}

def validatePosition(p):
    return ('x' in p and 'y' in p) or (('north' in p or 'south' in p) and ('east' in p or 'west' in p))

def convPos(p):
    if 'x' in p and 'y' in p: return p
    if 'north' in p:
        p['y'] = p['north']
        del p['north']
    elif 'south' in p:
        p['y'] = -p['south']
        del p['south']
    
    if 'east' in p:
        p['x'] = p['east']
        del p['east']
    elif 'west' in p:
        p['x'] = -p['west']
        del p['west']
    return p

def calDist(a, b, metric='euclidean'):
    x = a['x'] - b['x']
    y = a['y'] - b['y']
    if metric == 'manhattan':
        z = abs(x) + abs(y)
    else:
        z = (x*x + y*y)**0.5
    return z

@app.route('/distance', methods=['POST'])
def distance():
    body = request.get_json()
    if 'first_pos' not in body: abort(HTTPStatus.BAD_REQUEST)
    a = body['first_pos']
    if isinstance(a, str):
        if not a.startswith('robot#'): abort(HTTPStatus.BAD_REQUEST)
        p, n = a.split('#')
        n = int(n)
        if n not in robots: abort(HTTPStatus.FAILED_DEPENDENCY)
        a = robots[n]['position']
    elif not validatePosition(a): abort(HTTPStatus.BAD_REQUEST)
    else: a = convPos(a)
    
    if 'second_pos' not in body: abort(HTTPStatus.BAD_REQUEST)
    b = body['second_pos']
    if isinstance(b, str):
        if not b.startswith('robot#'): abort(HTTPStatus.BAD_REQUEST)
        p, n = b.split('#')
        n = int(n)
        if n not in robots: abort(HTTPStatus.FAILED_DEPENDENCY)
        b = robots[n]['position']
    elif not validatePosition(b): abort(HTTPStatus.BAD_REQUEST)
    else: b = convPos(b)
    metric = 'euclidean'
    if 'metric' in body:
        if body['metric'] != 'euclidean' and body['metric'] != 'manhattan': abort(HTTPStatus.BAD_REQUEST)
        else: metric = body['metric']
    result = calDist(a, b, metric)

    result = round(result,3)
    return jsonify(distance = result)
    

@app.route('/robot/<id>/position', methods=['PUT'])
def put_botpos(id):
    body = request.get_json()
    if 'position' not in body or not validatePosition(body['position']): abort(HTTPStatus.BAD_REQUEST)
    pos = body['position']
    pos = convPos(pos)
    robots[int(id)] = {'position': pos}
    return "", HTTPStatus.NO_CONTENT

@app.route('/robot/<id>/position', methods=['GET'])
def get_botpos(id):
    id = int(id)
    if id in robots:
        return jsonify(robots[id])
    else:
        return "", HTTPStatus.NOT_FOUND

@app.route('/nearest', methods=['POST'])
def nearest():
    body = request.get_json()
    a = body['ref_position']
    k = 1
    if 'k' in body: k = body['k']
    if len(robots) == 0:
        ans = []
    else:
        ans = sorted(map(lambda bot: [calDist(bot[1]['position'], a), bot[0]], robots.items()))
    ans = list(map(lambda x:x[1], ans))[:k]
    return jsonify(robot_ids=ans), HTTPStatus.OK

def calculateThreeCircleIntersection(c0, r0, c1, r1, c2, r2):
    if c0 == None: return False
    x0 = c0['x']
    y0 = c0['y']
    x1 = c1['x'] if c1 != None else None
    y1 = c1['y'] if c1 != None else None
    x2 = c2['x'] if c2 != None else None
    y2 = c2['y'] if c2 != None else None

    if r0 == 0:
        return {'x': x0, 'y': y0}
    elif r1 == 0:
        return {'x': x1, 'y': y1}
    elif r2 == 0:
        return {'x': x2, 'y': y2}
    if x1 == None: return False
    EPSILON = 0.0001
    dx = x1 - x0
    dy = y1 - y0

    d = ((dy*dy) + (dx*dx)) ** 0.5

    if d > (r0 + r1): return False
    if d < abs(r0 - r1): return False

    a = ((r0*r0) - (r1*r1) + (d*d)) / (2.0 * d)

    point2_x = x0 + (dx * a/d)
    point2_y = y0 + (dy * a/d)

    h = ((r0*r0) - (a*a)) ** 0.5

    rx = -dy * (h/d)
    ry = dx * (h/d)

    intersectionPoint1_x = point2_x + rx
    intersectionPoint2_x = point2_x - rx
    intersectionPoint1_y = point2_y + ry
    intersectionPoint2_y = point2_y - ry

    # print("INTERSECTION Circle1 AND Circle2:", "(", intersectionPoint1_x, ",", intersectionPoint1_y, ")", " AND (", intersectionPoint2_x , "," , intersectionPoint2_y , ")")
    if abs(intersectionPoint1_x - intersectionPoint2_x) < EPSILON and abs(intersectionPoint1_y - intersectionPoint2_y) < EPSILON:
        return {'x': intersectionPoint1_x, 'y': intersectionPoint1_y}
    if x2 == None: return False

    dx = intersectionPoint1_x - x2
    dy = intersectionPoint1_y - y2
    d1 = ((dy*dy) + (dx*dx)) ** 0.5

    dx = intersectionPoint2_x - x2
    dy = intersectionPoint2_y - y2
    d2 = ((dy*dy) + (dx*dx)) ** 0.5

    if abs(d1 - r2) < EPSILON:
        ans = {'x': intersectionPoint1_x, 'y': intersectionPoint1_y}
    elif abs(d2 - r2) < EPSILON:
        ans = {'x': intersectionPoint2_x, 'y': intersectionPoint2_y}
    else: ans = False
    return ans


aliens = {}
@app.route('/alien/<id>/report', methods=['POST'])
def alienReport(id):
    body = request.get_json()
    if id not in aliens: aliens[id] = {}
    aliens[id][body['robot_id']] = body['distance']
    return '', HTTPStatus.OK

@app.route('/alien/<id>/position', methods=['GET'])
def alienPos(id):
    #calcPosition
    if id not in aliens: abort(HTTPStatus.FAILED_DEPENDENCY)
    data = aliens[id] # {bot: distance, bot: distance}
    bots = [*data.keys()]
    c0 = d0 = c1 = d1 = c2 = d2 = None
    if len(bots) > 0:
        c0 = robots[bots[0]]['position']
        d0 = data[bots[0]]
    if len(bots) > 1:
        c1 = robots[bots[1]]['position']
        d1 = data[bots[1]]
    if len(bots) > 2:
        c2 = robots[bots[2]]['position']
        d2 = data[bots[2]]
    ans = calculateThreeCircleIntersection(c0, d0, c1, d1, c2, d2)
    if ans == False: abort(HTTPStatus.FAILED_DEPENDENCY)

    return jsonify(ans), HTTPStatus.OK


#### closest pair
def bruteForce(P):
    n = len(P)
    min = 9999999999
    for i in range(n):
        for j in range(i+1, n):
            d = calDist(P[i], P[j])
            if d < min:
                min = d
    return min

def stripClosest(ps, d):
    min = d
    size = len(ps)
    ps.sort(key=lambda x:x['y'])
    for i in range(size):
        for j in range(i+1, size):
            if ps[j]['y'] - ps[i]['y'] < min: break
            d = calDist(ps[i], ps[j])
            if d < min:
                min = d
    return min

def closestUtil(P):
    n = len(P)
    if (n <= 3):
        return bruteForce(P)
    mid = n//2
    midPoint = P[mid]
    dl = closestUtil(P[:mid])
    dr = closestUtil(P[mid:])
    d = min([dl, dr])
    strip = []
    for i in range(n):
        if abs(P[i]['x'] - midPoint['x'] < d):
            strip.append(P[i])

    return min(d, stripClosest(strip, d) )


def closest(ps):
    ps.sort(key=lambda x:x['x'])
    return closestUtil(ps)

@app.route('/closestpair', methods=['GET'])
def closestpair():
    if len(robots) < 2: abort(HTTPStatus.FAILED_DEPENDENCY)
    ps = [*map(lambda x:x['position'], robots.values())]
    ans = closest(ps)
    return jsonify(distance = ans)