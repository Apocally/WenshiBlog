#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Wenshi'

import logging; logging.basicConfig(level=logging.INFO)
import asyncio, aiomysql


async def create_pool(**kw):
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1)
    )


async def select(sql,args,size=None):
    global __pool
    with (await __pool) as conn:
        # Return dict
        cur = conn.cursor(aiomysql.DictCursor)
        await cur.execute(sql.replace('?', '%s'), args)
        if size:
            rs = await cur.fetchmany(size)
        else:
            rs = await cur.fetchall()
        await cur.close()
        return rs


async def execute(sql, args):
    global __pool
    try:
        with (await __pool) as conn:
            cur = conn.cursor()
            await cur.execute(sql.replace('?', '%s'), args)
            # Return column affected num
            affected = cur.rowcount()
            await cur.close()
    except BaseException as e:
        raise e
    return affected


# type is the metaclass of all classes in python
# for class Users, Blogs and Comments. Therefore name, bases, attrs need to define when new the class.
class ModelMetaClass(type):
    # metaclass: __new__()method to new a class
    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)        # attrs = {'id': AField, 'name':BField, 'email':CField}
        tableName = attrs.get['__table__', None] or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        mappings = {}
        # the field names of non-primarykeys
        fields = []
        # the field name of primarykey, unique
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    else:
                        primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        # remove information that has been included in 'mappings' from 'attrs'
        # we need a new 'attrs', which contains '__mappings__', '__table__', '__primary_key__', '__fields__' and sql
        for k in mappings.keys():
            attrs.pop(k)

        escaped_fields = list(map(lambda f: '`%s`' % f, fields))





# user.id = user['id'], (Attributes)getValue, (Attributes)getValueOrDefault
class Model(dict, metaclass=ModelMetaClass):

    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            value = self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute %s" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            # field.default could be a function or a value
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value


class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):
    def __init__(self, name=None, column_type='varchar(100)', primary_key=False, default=None):
        super(StringField,self).__init__(name, column_type, primary_key, default)


class IntegerField(Field):
    pass