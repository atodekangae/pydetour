#!/usr/bin/env python3
import sys
import ctypes
from functools import partial
if sys.version_info < (3, 8):
    import warnings
    warnings.warn('pydetour would work only partially in Python below 3.8')


class PyObject(ctypes.Structure):
    pass

class PyTypeObject(ctypes.Structure):
    pass

PyObject._fields_ = [
    ('ob_refcnt', ctypes.c_ssize_t),
    ('ob_type', ctypes.POINTER(PyTypeObject)),
]

PyTypeObject._fields_ = [
    ('ob_base', PyObject),
    ('ob_size', ctypes.c_ssize_t),

    ('tp_name', ctypes.c_char_p),
    ('tp_basicsize', ctypes.c_ssize_t),
    ('tp_itemsize', ctypes.c_ssize_t),
    ('tp_dealloc', ctypes.c_void_p),
    ('tp_vectorcall_offset', ctypes.c_ssize_t),
    ('tp_getattr', ctypes.c_void_p),
    ('tp_setattr', ctypes.c_void_p),
    ('tp_as_async', ctypes.c_void_p),
    ('tp_repr', ctypes.c_void_p),
    ('tp_as_number', ctypes.c_void_p),
    ('tp_as_sequence', ctypes.c_void_p),
    ('tp_as_mapping', ctypes.c_void_p),
    ('tp_hash', ctypes.c_void_p),
    ('tp_call', ctypes.c_void_p),
    ('tp_str', ctypes.c_void_p),
    ('tp_getattro', ctypes.c_void_p),
    ('tp_setattro', ctypes.c_void_p),
    ('tp_as_buffer', ctypes.c_void_p),
    ('tp_flags', ctypes.c_void_p),
    ('tp_doc', ctypes.c_void_p),
    ('tp_traverse', ctypes.c_void_p),
    ('tp_clear', ctypes.c_void_p),
    ('tp_richcompare', ctypes.c_void_p),
    ('tp_weaklistoffset', ctypes.c_void_p),
    ('tp_iter', ctypes.c_void_p),
    ('iternextfunc', ctypes.c_void_p),
    ('tp_methods', ctypes.c_void_p),
    ('tp_members', ctypes.c_void_p),
    ('tp_getset', ctypes.c_void_p),
    ('tp_base', ctypes.c_void_p),
    ('tp_dict', ctypes.c_void_p),
    ('tp_descr_get', ctypes.c_void_p),
    ('tp_descr_set', ctypes.c_void_p),
    ('tp_dictoffset', ctypes.c_void_p),
    ('tp_init', ctypes.c_void_p),
    ('tp_alloc', ctypes.c_void_p),
    ('tp_new', ctypes.c_void_p),
    ('tp_free', ctypes.c_void_p),
    ('tp_is_gc', ctypes.c_void_p),
    ('tp_bases', ctypes.py_object),
    ('tp_mro', ctypes.py_object),
    ('tp_cache', ctypes.py_object),
    ('tp_subclasses', ctypes.py_object),
    ('tp_weaklist', ctypes.py_object),
    ('tp_del', ctypes.c_void_p),
    ('tp_version_tag', ctypes.c_uint),
    ('tp_finalize', ctypes.c_void_p),
    ('tp_bases', ctypes.py_object),
    ('tp_vectorcall', ctypes.c_void_p)
]

Py_TPFLAGS_HAVE_VECTORCALL = 1 << 11


def Py_TYPE(obj) -> ctypes.POINTER(PyTypeObject):
    return PyObject.from_address(id(obj)).ob_type

def has_vectorcall(tp: ctypes.POINTER(PyTypeObject)) -> bool:
    return (ctypes.pythonapi.PyType_GetFlags(tp) & Py_TPFLAGS_HAVE_VECTORCALL) != 0

def get_vectorcall_ptr(func):
    tp = Py_TYPE(func)
    assert has_vectorcall(tp)
    offset = tp.contents.tp_vectorcall_offset
    assert offset > 0
    pointer = ctypes.c_void_p.from_address(id(func) + offset)
    #pointer = ctypes.cast(id(func) + offset, ctypes.POINTER(ctypes.c_void_p))
    return pointer

tpcallfunc = ctypes.PYFUNCTYPE(
    ctypes.py_object,
    ctypes.py_object, ctypes.py_object, ctypes.c_void_p) # the last argument might be NULL
vectorcallfunc = ctypes.PYFUNCTYPE(
    ctypes.py_object,
    ctypes.py_object, ctypes.POINTER(ctypes.py_object), ctypes.c_size_t, ctypes.c_void_p)

PY_VECTORCALL_ARGUMENTS_OFFSET = 1 << (8 * ctypes.sizeof(ctypes.c_size_t) - 1)

def PyVectorcall_NARGS(n):
    return n & (~PY_VECTORCALL_ARGUMENTS_OFFSET)

def address_from_pointer(p):
    return ctypes.cast(p, ctypes.c_void_p).value

PyThreadState_Get = ctypes.PYFUNCTYPE(ctypes.c_void_p)((
    'PyThreadState_Get', ctypes.pythonapi
))
try:
    _PyObject_MakeTpCall = ctypes.PYFUNCTYPE(
        ctypes.py_object,
        ctypes.c_uint64,
        ctypes.py_object, ctypes.POINTER(ctypes.py_object), ctypes.c_ssize_t,
        ctypes.c_void_p # PyObject *, but it can be NULL
    )((
        '_PyObject_MakeTpCall', ctypes.pythonapi
    ))
except:
    _PyObject_MakeTpCall = None

tpcall_modified_typeobjects = {}
hook_refs = {}

def hook_func(hookee, get_hooker):
    tp = Py_TYPE(hookee)
    references = []
    if has_vectorcall(tp):
        pointer = get_vectorcall_ptr(hookee)
        real_vectorcallfunc_addr = pointer.value
        is_hooked = False
        def kwargs_to_kwnames(args_array, base, kwargs):
            kwnames_tuple = [None] * len(kwargs)
            for i, (k, v) in enumerate(kwargs.items()):
                kwnames_tuple[i] = k
                args_array[base + i] = v
            return tuple(kwnames_tuple)

        if real_vectorcallfunc_addr is None:
            def _hookee(*args, **kwargs):
                tstate = PyThreadState_Get()
                args_array = (ctypes.py_object * (len(args) + len(kwargs) + 1))()
                for i, arg in enumerate(args):
                    args_array[i] = arg
                if kwargs:
                    kwnames_tuple = kwargs_to_kwnames(args_array, len(args), kwargs)
                    kwnames = id(kwnames_tuple)
                else:
                    kwnames = None
                return _PyObject_MakeTpCall(tstate, hookee, args_array, len(args), kwnames)
        else:
            real_vectorcallfunc_callable = ctypes.cast(real_vectorcallfunc_addr, vectorcallfunc)
            def _hookee(*args, **kwargs):
                args_array = (ctypes.py_object * (len(args) + len(kwargs) + 1))()
                if kwargs:
                    kwnames_tuple = kwargs_to_kwnames(args_array, len(args), kwargs)
                    kwnames = id(kwnames_tuple)
                else:
                    kwnames = None
                for i in range(len(args)):
                    args_array[i] = args[i]
                ret = real_vectorcallfunc_callable(
                    hookee,
                    args_array,
                    len(args), # | PY_VECTORCALL_ARGUMENTS_OFFSET,
                    kwnames
                )
                return ret
        def _hooker(callable_obj, args, nargsf, kwnames):
            nargs = PyVectorcall_NARGS(nargsf)
            kwargs = {}
            if kwnames is not None:
                kwnames_pyobject = ctypes.cast(kwnames, ctypes.py_object).value
                for i, name in enumerate(kwnames_pyobject):
                    kwargs[name] = args[nargs+i]
            return hooker(*[args[i] for i in range(nargs)], **kwargs)
        def _unhook():
            nonlocal is_hooked
            if is_hooked:
                pointer.value = real_vectorcallfunc_addr
                is_hooked = False
            else:
                raise RuntimeError('function is not hooked')
        def _hook():
            nonlocal is_hooked
            if not is_hooked:
                pointer.value = hooker_addr
                is_hooked = True
            else:
                raise RuntimeError('function is alrady hooked')
        f = vectorcallfunc(_hooker)
        references.append(_hooker)
        references.append(f)
        hooker_addr = address_from_pointer(f)
    else:
        obj_addr = id(hookee)
        tp_addr = address_from_pointer(tp)
        if tp_addr in tpcall_modified_typeobjects:
            orig_tpcall, obj_to_hooker = tpcall_modified_typeobjects[tp_addr]
        else:
            tpcall = tp.contents.tp_call
            if not tpcall:
                raise Exception()
            orig_tpcall = ctypes.cast(tpcall, tpcallfunc)
            obj_to_hooker = {}
            def _hooker(obj, argstuple, kwdict):
                hooker_func = obj_to_hooker.get(id(obj))
                if hooker_func is None:
                    ret = orig_tpcall(obj, argstuple, kwdict)
                    return ret
                else:
                    if kwdict is not None:
                        kwargs = ctypes.cast(kwdict, ctypes.py_object).value
                    else:
                        kwargs = {}
                    return hooker_func(*argstuple, **kwargs)
            tp.contents.tp_call = address_from_pointer(tpcallfunc(_hooker))
            references.append(_hooker)
            tpcall_modified_typeobjects[tp_addr] = (orig_tpcall, obj_to_hooker)
        def _hookee(*args, **kwargs):
            if len(kwargs) == 0:
                kwdict = None
            else:
                kwdict = id(kwargs)
            ret = orig_tpcall(hookee, args, kwdict)
            return ret
        def _hook():
            if obj_addr in obj_to_hooker:
                raise RuntimeError()
            else:
                obj_to_hooker[obj_addr] = hooker
        def _unhook():
            if obj_addr in obj_to_hooker:
                obj_to_hooker.pop(obj_addr)
            else:
                raise RuntimeError()
    hooker = get_hooker(_hookee)
    key = (id(hookee), id(hooker))
    hook_refs[key] = references
    _hook()
    def _finalize():
        _unhook()
        hook_refs.pop(key)
    return _finalize

def hook(*args):
    if len(args) == 2:
        return hook_func(*args)
    elif len(args) == 1:
        hookee, = args
        return partial(hook_func, hookee)
    else:
        raise TypeError()

def main():
    from pprint import pprint
    import os
    assert_working = False
    try:
        assert False
    except AssertionError:
        assert_working = True
    if not assert_working:
        raise RuntimeError('assert not working!')
    non_vectorcall_callables = {
        n for n,f in __builtins__.__dict__.items()
        if callable(f) and not has_vectorcall(Py_TYPE(f))
    }
    pprint(non_vectorcall_callables)
    ret = memoryview(b'asdf')
    @hook(memoryview)
    def unhook_memoryview(orig_memoryview):
        def fake_memoryview(obj):
            print('fake_memoryview:', obj)
            ret = list(orig_memoryview(obj))
            ret.insert(0, 0)
            return ret
        return fake_memoryview
    assert memoryview(b'asdf') == [0] + list(b'asdf')
    unhook_memoryview()
    assert memoryview(b'asdf') == ret
    # if memoryview in non_vectorcall_callables:
    def get_fake_memoryview(orig_memoryview):
        def fake_memoryview(obj):
            print('fake_memoryview:', obj)
            ret = list(orig_memoryview(obj))[::-1]
            return ret
        return fake_memoryview
    if True:
        unhook = hook(memoryview, get_fake_memoryview)
        assert list(memoryview(b'asdf')) == list(b'asdf')[::-1]
        print('success')
        unhook()
        print('unhook() done')
    def get_fake_memoryview(orig_memoryview):
        def fake_memoryview(**kwargs):
            print('fake_memoryview:', kwargs)
            ret = list(orig_memoryview(**kwargs))[::-1]
            return ret
        return fake_memoryview
    unhook = hook(memoryview, get_fake_memoryview)
    assert list(memoryview(object=b'asdf')) == list(b'asdf')[::-1]
    unhook()
    # if reversed in non_vectorcall_callables:
    def get_fake_reversed(orig_reversed):
        def fake_reversed(xs, test=None):
            print('fake_reversed')
            ret = list(orig_reversed(xs))
            ret.insert(0, 'wut')
            return ret
        return fake_reversed
    unhook = hook(reversed, get_fake_reversed)
    ret = reversed(range(10), test=123)
    print(ret)
    assert ret == ['wut'] + list(range(10))[::-1]
    print(repr(StopIteration()))
    unhook()
    def get_fake_os_listdir(os_listdir):
        def fake_os_listdir(path, test=None):
            print('fake_os_listdir({!r})'.format(path), test)
            ret1 = os_listdir(path)
            ret2 = os_listdir(path=path)
            assert ret1 == ret2
            ret1.insert(0, '<fake>')
            return ret1
        return fake_os_listdir
    ret_unaffected = os.listdir('.')
    unhook = hook(os.listdir, get_fake_os_listdir)
    ret_affected = os.listdir('.')#, test=123)
    print(ret_affected)
    assert ['<fake>']+ret_unaffected == ret_affected
    unhook()
    ret = os.listdir('.')
    print(ret)
    assert ret == ret_unaffected

if __name__ == '__main__':
    main()
