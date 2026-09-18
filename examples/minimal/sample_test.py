import unittest
from sample import greeting
class ExampleTest(unittest.TestCase):
    def test_greeting(self): self.assertEqual("Hello, web!", greeting("web"))
if __name__ == "__main__": unittest.main()
