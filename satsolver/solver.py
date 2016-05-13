from __future__ import print_function
import re
from satispy import Variable, Cnf
from satispy.solver import Minisat
import pycosat

flags = []
req_use = """|| (a b c)
            || (g d f)"""

if flags == []: flags = re.findall(r'\w+', req_use)
sorted(flags, key=len)
flags.reverse()

print('\n', req_use, '\n')

i = 1
dict = {}
revr = {}

for k in flags:
    dict[k] = i
    revr[i] = k
    i += 1

print("The key is:", revr)

def getToken(eq):
    eq = eq.strip()
    if eq == "": return None, eq
    if eq[0] == '(':
        brack = 0
        index = 0
        for ch in eq:
            if ch == '(':
                brack += 1
            elif ch == ')':
                brack -= 1
            index += 1
            if brack == 0:
                break
        return ( eq[:index], eq[index:] )
    elif re.match(r'^[a-zA-Z!]', eq):
        token = re.findall(r'^[a-zA-Z!]+', eq)[0]
        length = len(token)
        return ( eq[:length], eq[length:] )
    else:
        print("No token found:", eq)
        exit(0)

def solveToken(eq):
    eq = eq.strip()
    token, eq = getToken(eq)
    if token is None: return None, eq

    if token[0] == '!':
        return ( -Variable(token[1:].strip()), eq )
    if re.match(r'^[a-zA-Z]', token):
        return ( Variable(token.strip()), eq )
    if token[0] == '(':
        return ( solve(token[1:-1]), eq )

    print("I failed: ", token, eq)
    exit(0)

def all_or(eq):
    eq = eq.strip()[1:-1]
    ret = Cnf()

    token, eq = solveToken(eq)
    while token is not None:
        ret = ret | token
        token, eq = solveToken(eq)

    return ret

def all_xor(eq):
    eq = eq.strip()[1:-1]
    lst = []

    token, eq = solveToken(eq)
    while token is not None:
        lst.append(token)
        token, eq = solveToken(eq)
    
    ret = Cnf()
    for a in lst:
        tmp = Cnf()
        for b in lst:
            if a == b:
                tmp = tmp & b
            else:
                tmp = tmp & (-b)
        ret = ret | tmp
    return ret

def solve(eq):
    eq = eq.strip()
    if eq == '': return Cnf()

    op = re.findall(r'^(\^\^|\|\|)', eq)
    if op:
        op = op[0]
        if op == '||':
            var, eq = getToken(eq[2:])
            assert var[0] == '(' and var[-1] == ')'
            result = all_or(var)
        elif op == '^^':
            var, eq = getToken(eq[2:])
            assert var[0] == '(' and var[-1] == ')'
            result = all_xor(var)
        return result & solve(eq)

    op = re.findall(r'^[a-zA-Z]+\s*\?', eq)
    if op:
        op = op[0]
        eq = eq[len(op):]
        var1 = Variable(op[:-1].strip())
        var2, eq = solveToken(eq)
        return (var1 >> var2) & solve(eq)

    op = re.findall(r'^[a-zA-Z]+', eq)
    if op:
        op = op[0]
        eq = eq[len(op):]
        var = Variable(op.strip())
        return var & solve(eq)

for i in range(0, 10000):
    cnf_out = solve(req_use)
    cnf_str = str(cnf_out)

    # print(cnf_str)

    for key in dict:
        cnf_str = cnf_str.replace(key, str(dict[key]))
        # print(key, dict[key])

    cnf_str = cnf_str[1:-1]
    cnf_lst = cnf_str.split(') & (')

    for i in range(len(cnf_lst)):
        cnf_lst[i] = [int(k) for k in cnf_lst[i].split(' | ')]

    k = (list(pycosat.itersolve(cnf_lst)))
