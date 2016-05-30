from __future__ import print_function
import re
from satispy import Variable, Cnf
import pycosat


# Provide all flags here in this array, or they will be
# extracted from req_use string
flags = []

# REQUIRED_USE variable value for which the combinations
# are being generated
req_use = "?? (a b c) ^^ (b c d)"

# If flags aren't provided, match words from REQUIRED_USE
if flags == []: flags = re.findall(r'\w+', req_use)
# Remove duplicates
flags = list(set(flags))
# sort reverse to length (so that they can be replaced in
# this order by numbers later)
sorted(flags, key=len)
flags.reverse()

print('\n', req_use, '\n')

i = 1
dict = {}

# Assign a number to each keyword (to send to pycosat as
# it accepts cnf in form of numbers )
for k in flags:
    dict[k] = i
    i += 1

print("The key is:", dict)

# Separates out a single token from a string and returns
# the two pieces. For eg.
# if string is: "flag1 (abc cde)"
# return ("flag1", "(abc cde)")
# If string is: "(abc def (ghi jkl) (abc)) ^^ (abc)"
# return ("(abc def (ghi jkl) (abc))", "^^ (abc)")
def getToken(eq):
    eq = eq.strip()
    # Empty string case
    if eq == "": return None, eq

    # Count to find matching bracket
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
    # If token is a flag name instead of bracket
    # It may also contain a '!' for a NOT
    elif re.match(r'^[\w!]', eq):
        token = re.findall(r'^[\w!]+', eq)[0]
        length = len(token)
        return ( eq[:length], eq[length:] )

    # This should ideally never be encountered
    else:
        print("No token found:", eq)
        exit(0)

def solveToken(eq):
    eq = eq.strip()

    # Request for a new token.
    token, eq = getToken(eq)
    if token is None: return None, eq

    # If the variable is a negation, Create a negated
    # variable. Return the relevant variable obj and the
    # remaining string
    if token[0] == '!':
        return ( -Variable(token[1:].strip()), eq )

    # If no negation is present, return just the variable
    if re.match(r'^[\w]', token):
        return ( Variable(token.strip()), eq )

    # If the token is a bracketed group, recursively
    # solve it
    if token[0] == '(':
        return ( solve(token[1:-1]), eq )

    # This should ideally never be encountered
    print("I failed: ", token, eq)
    exit(0)

# This is the case of "|| (aa bb (cc dd))"
# The input eq in above case would be: "(aa bb (cc dd))"
def all_or(eq):
    # Remove the parentheses
    eq = eq.strip()[1:-1]
    # Create a blank Cnf object
    ret = Cnf()

    # Extract next token and OR with ret variable until you
    # run out of tokens
    token, eq = solveToken(eq)
    while token is not None:
        ret = ret | token
        token, eq = solveToken(eq)

    return ret

# This is the case of "^^ (aa bb (cc dd))"
# The input eq in above case would be: "(aa bb (cc dd))"
# Output would be corresponding to EXACTLY one out of
# aa, bb, (cc dd)
def all_xor(eq):
    # Remove the parentheses
    eq = eq.strip()[1:-1]
    # List to hold all SOLVED tokens: [aa, bb, (cc & dd)]
    lst = []

    token, eq = solveToken(eq)
    while token is not None:
        lst.append(token)
        token, eq = solveToken(eq)
    
    ret = Cnf()
    # Best explained by example: for [a, b, c]
    # it would create
    # (a & -b & -c) | (-a & b & -c) | (-a & -b & c)
    # EXACTLY one of [a, b, c]
    for a in lst:
        tmp = Cnf()
        for b in lst:
            if a == b:
                tmp = tmp & b
            else:
                tmp = tmp & (-b)
        ret = ret | tmp
    return ret

# Almost same as all_xor
# One extra case: ALL negation (NONE out of [a, b, c])
def at_most(eq):
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
    # Same as xor_all till here

    tmp = Cnf()
    # One extra case in which all are negative
    for b in lst:
        tmp = tmp & (-b)
    ret = ret | tmp

    return ret

# This is the primary solve function that is called
# on the req_use string
# The string can start with following:
# 1. || or ?? or ^^:
#
#    i.   || :
#             strip the first two characters,
#             extract the next token and call all_or
#    ii.  ^^ :
#             strip the first two characters,
#             extract the next token and call all_xor
#    iii. ?? :
#             strip the first two characters,
#             extract the next token and call at_most
#
# 2. flag1? (abc def) (....)
#     
#     Beak into "flag1?" and "(abc def) (....)"
#     Make flag1 into a variable var1
#     Solve the first token "(abc def)" to var2
#     Condition1 is var1 => var2 (implication)
#     Condition2 is (...) solved by `solve` recursively
#     Return AND of Condition 1 & 2
# 3. normal_flag
#
#     Most probably shouldn't occur (if it's compulsory
#     then it shouldn't be a USE flag). But if it does,
#     convert to variable and & with recursively solved
#     rest of the equation.
def solve(eq):
    eq = eq.strip()
    if eq == '': return Cnf()

    op = re.findall(r'^(\^\^|\|\||\?\?)', eq)
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
        elif op == '??':
            var, eq = getToken(eq[2:])
            assert var[0] == '(' and var[-1] == ')'
            result = at_most(var)
        return result & solve(eq)

    op = re.findall(r'^[\w]+\s*\?', eq)
    if op:
        op = op[0]
        eq = eq[len(op):]
        var1 = Variable(op[:-1].strip())
        var2, eq = solveToken(eq)
        return (var1 >> var2) & solve(eq)

    op = re.findall(r'^[\w]+', eq)
    if op:
        op = op[0]
        eq = eq[len(op):]
        var = Variable(op.strip())
        return var & solve(eq)

    # This should ideally never be encountered
    print("I failed", eq);
    exit(0)

# Generate the needed boolean expression
cnf_out = solve(req_use)

# str(object) gives a string in CNF form
cnf_str = str(cnf_out)

# Replace all flags with numerical equivalent
for key in dict:
    cnf_str = cnf_str.replace(key, str(dict[key]))

# Convert to form needed by pycosat
cnf_str = cnf_str[1:-1]
cnf_lst = cnf_str.split(') & (')
for i in range(len(cnf_lst)):
    cnf_lst[i] = [int(k) for k in cnf_lst[i].split(' | ')]

# Generate all possible solutions to the equation
k = (list(pycosat.itersolve(cnf_lst)))
print(k)
