import unittest
import container
import control
import helpers
import solver
from satispy import Cnf


def reduceCnf(cnf):
    """
    I just found a remarkably large bug in my
    SAT solver and found an interesting solution.
    Remove all b | -b
    (-b | b) & (b | -a) & (-b | a) & (a | -a)
    becomes 
    (b | -a) & (-b | a)
    Remove all (-e) & (-e)
    (-e | a) & (-e | a) & (-e | a) & (-e | a)
    becomes
    (-e | a)
    (-b | b | c) becomes nothing, not (c)
    """
    if type(cnf) is str:
        return cnf

    output = Cnf()
    for x in cnf.dis:
        dont_add = False
        for y in x:
            for z in x:
                if z == -y:
                    dont_add = True
                    break
            if dont_add: break
        if dont_add: continue
        if x not in output.dis:
            output.dis.append(x)
    return output


class TestSolver(unittest.TestCase):
    """
    Test suite for boolean satisfiabiity
    problem solver
    """
    def testGetToken(self):
        self.assertEqual(solver.getToken("flag1 (abc cde)"), ("flag1", "(abc cde)"))
        self.assertEqual(solver.getToken("(abc def (ghi jkl) (abc)) ^^ (abc)"),
                ("(abc def (ghi jkl) (abc))", "^^ (abc)"))

    def testSolveToken(self):
        self.assertEqual([str(k) for k in solver.solveToken("a b c")], ['a', 'b c'])
        self.assertEqual([str(k) for k in solver.solveToken("( a b ) b c")],
                ['(a) & (b)', 'b c'])
        self.assertEqual([str(k) for k in solver.solveToken("!a b c")],
                ['-a', 'b c'])
        self.assertEqual(
                [str(reduceCnf(k)) for k in solver.solveToken("(^^ ( a b )) b c")],
                ['(a | b) & (-a | -b)', 'b c'])

    def testAllOr(self):
        self.assertEqual(str(solver.all_or("(a b c)")), '(a | c | b)')
        self.assertEqual(str(solver.all_or("(a (b c) d)")), '(a | b | d) & (a | c | d)')

    def testAllXor(self):
        self.assertEqual(str(reduceCnf(solver.all_xor("(a b)"))), '(a | b) & (-a | -b)')
        self.assertEqual(str(reduceCnf(solver.all_xor("(a b c)"))), " ".join("""
                (a | c | b) & (a | -b | -c) & (-a | -b) & (-a | -b | c) &
                (-a | -b | -c) & (-b | -c) & (-a | -c) & (-a | -c | b)
                """.split()))

    def testAtMost(self):
        self.assertEqual(str(reduceCnf(solver.at_most("(a b c)"))),
                " ".join("""(a | -b | -c) & (-a | -b) & (-a | -b | -c) &
                (-a | -b | c) & (-b | -c) & (-a | -c) & (-a | -c | b)""".split()))
        self.assertEqual(str(reduceCnf(solver.at_most("(a (b c) d)"))),
                " ".join("""
                (a | -b | -c | -d) & (-a | -b | -c) & (-a | -b | -c | -d) &
                (-a | -b | -c | d) & (-b | -c | -d) & (-a | -d) & (-a | b | -d) &
                (-a | c | -d)""".split()))

    def testMain(self):
        self.assertEqual(solver.main("a b c"), [['b', 'c', 'a']])
        self.assertEqual(solver.main("?? ( a b c )"), [
                    ['-b', '-c', '-a'], ['-b', '-c', 'a'],
                    ['-b', 'c', '-a'], ['b', '-c', '-a'] ])
        self.assertEqual(solver.main("a !b ^^ (b c) ?? (c d)"), [['-d', '-b', 'c', 'a']])



class TestContainer(unittest.TestCase):
    """
    Tests for functions in container.py
    """

    def testAppendLog(self):
        open("/tmp/emerge_logs", "w").write("")
        container.folder_name = "/tmp/"
        container.append_log("Hi")
        self.assertEqual(open("/tmp/emerge_logs").read(), "Hi\n")
        container.append_log("Hi\n")
        self.assertEqual(open("/tmp/emerge_logs").read(), "Hi\nHi\n")
        container.append_log("Arg1", "Arg2", "Arg3")
        self.assertEqual(open("/tmp/emerge_logs").read(), "Hi\nHi\nArg1 Arg2 Arg3\n")
        container.append_log(["arg1", "arg2"])
        self.assertEqual(open("/tmp/emerge_logs").read(), "Hi\nHi\nArg1 Arg2 Arg3\n['arg1', 'arg2']\n")

    def testAbsFlag(self):
        self.assertEqual(container.abs_flag("abc"), "abc")
        self.assertEqual(container.abs_flag("-abc"), "abc")

    def testGetHash(self):
        for i in range(10):
            self.assertEqual(len(container.get_hash()), 8)
            self.assertNotEqual(container.get_hash(), container.get_hash())

    def testB64Encode(self):
        self.assertEqual(container.b64encode("Hello World"), "SGVsbG8gV29ybGQ")
        self.assertEqual(container.b64encode("Hit"), "SGl0")


if __name__ == '__main__':
    unittest.main()
