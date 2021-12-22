# pydetour: Redirect any callable objects in Python
*pydetour* is a pure-Python library for redirecting any callable object -- builtin functions included -- to an arbitrary function, *without replacing the reference to the to-be-redirected function*. Works on Python 3.8 and above.

## Installation
```
pip install pydetour
```

... or simply put `pydetour.py` in a PYTHON_PATH.

## Example
Let us see what it takes to redirect calls to `os.listdir` using this library.

```python
>>> from pydetour import hook
>>> def get_fake_os_listdir(os_listdir):
...   def fake_os_listdir(path):
...     print(f'fake_os_listdir({repr(path)})')
...     ret = os_listdir(path)
...     ret.insert(0, '<fake>')
...     return ret
...   return fake_os_listdir
...
```

`get_fake_os_listdir` is a function to pass to the library. Note that it takes an argument and returns a function. As you can infer, the argument is (or, more precicely, can be treated as) the original function and the returned function is the function to which calls to `os.listdir` are redirected.

```python
>>> import os
>>> os.listdir('.')
['pydetour.py', 'README.md', 'setup.py']
>>> ref = os.listdir
>>> unhook = hook(os.listdir, get_fake_os_listdir)
>>> ref is os.listdir
True
```

We hooked `os.listdir` by invoking `hook()` function from the library, which returns another function which reverses the effect.  By comparing the variable to which we had saved the reference of `os.listdir` with `os.listdir` after hooking, we can confirm that they are identical.

```python
>>> os.listdir('.')
fake_os_listdir('.')
['<fake>', 'pydetour.py', 'README.md', 'setup.py']
>>> unhook()
>>> os.listdir('.')
['pydetour.py', 'README.md', 'setup.py']
```

However, calling `os.listdir` demonstrates that the call is indeed redirected to the function we defined earlier, as there is `<fake>` inserted in the beginning of the returned list. By calling the function returned by `hook()` we can undo the redirection.

## How it works
In order to understand how this library works, it is necessary to get to know how function invocation is treated in CPython 3.8 and above. The snippet shown below is the part of CPython in charge of handling function invocations. (The explanation given here is a simplified one, as it does not mention the case in which `tp_call` is called. Although we omit this case here, the library handles that as well.)

`Include/cpython/abstract.h`
```c
static inline PyObject *
_PyObject_VectorcallTstate(PyThreadState *tstate, PyObject *callable,
                           PyObject *const *args, size_t nargsf,
                           PyObject *kwnames)
{
    // snip
    func = PyVectorcall_Function(callable);
    // snip
    res = func(callable, args, nargsf, kwnames);
    return _Py_CheckFunctionResult(tstate, callable, res, NULL);
}
```

Here, `callable` is a pointer to a callable `PyObject` being invoked and `PyVectorcall_Function` is a function for retrieving `tp_vectorcall`, a function pointer, from a given `PyObject`. After retrieving the `tp_vectorcall`, it is called with the arguments passed to `callable`.

With this in mind, it is easy to see that if we could modify what `PyVectorcall_Function` returns for `callable`, we would be able to redirect all the invocations of `callable`, which is exactly what this library does.

To achieve the goal, this library makes an extensive (ab)use of ctypes for manipulating internal Python objects.
