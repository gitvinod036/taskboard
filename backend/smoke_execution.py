import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from taskflow.execution import judge


class P:
    time_limit_seconds = 5


CASES = [
    type('T', (), {'input': 'hello', 'expected_output': 'HELLO', 'is_hidden': False}),
]

JAVA = ('public class Main { public static void main(String[] a) '
        '{ System.out.println(new java.util.Scanner(System.in).next().toUpperCase()); } }')

CPP = ('#include <bits/stdc++.h>\nusing namespace std;\n'
       'int main(){string s; cin>>s; for(auto&c:s)c=toupper(c); cout<<s<<endl;}')

JS = "const fs=require('fs');console.log(fs.readFileSync(0,'utf8').trim().toUpperCase())"

o = judge(P(), 'python', 'print(input().upper())', CASES)
print('python     :', o.status, o.passed_tests, f'{o.execution_time}s', f'{o.memory_used}MB')

oj = judge(P(), 'java', JAVA, CASES)
print('java       :', oj.status, oj.passed_tests, f'{oj.execution_time}s', f'{oj.memory_used}MB')

oc = judge(P(), 'cpp', CPP, CASES)
print('cpp        :', oc.status, oc.passed_tests, f'{oc.execution_time}s', f'{oc.memory_used}MB')

s = judge(P(), 'javascript', JS, CASES)
print('javascript :', s.status, s.passed_tests, f'{s.execution_time}s', f'{s.memory_used}MB')

w = judge(P(), 'python', "print(input().upper() + '!')", CASES)
print('wrong      :', w.status, '|', w.feedback.splitlines()[0])

c = judge(P(), 'cpp', 'int main( {', CASES)
print('compile-err:', c.status)

r = judge(P(), 'python', 'raise SystemExit(3)', CASES)
print('runtime    :', r.status, '|', r.feedback[:50])

t = judge(P(), 'python', 'while True: pass', CASES)
print('timeout    :', t.status, '|', t.feedback[:60])

m = judge(P(), 'python', 'x = [0] * 60_000_000', CASES)
print('memory     :', m.status, '|', m.feedback[:60])
