#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time, re, hashlib, json, logging
from coroweb import get, post
from models import User, Blog, Comment, next_id, Tag, Tagmap
from apis import APIError, APIValueError, APIPermissionError, Page, APIResourceNotFoundError
from aiohttp import web
from config import configs
import misaka as m
from pygments import highlight
from pygments.formatters import HtmlFormatter, ClassNotFound
from pygments.lexers import get_lexer_by_name


__author__ = 'Wenshi'


_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret


class HighlighterRenderer(m.HtmlRenderer):
    def blockcode(self, text, lang):
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except ClassNotFound:
            lexer = None
        if lexer:
            formatter = HtmlFormatter(style='colorful')
            return highlight(text, lexer, formatter)
        # default
        return '\n<pre><code>{}</code></pre>\n'.format(
                            text.strip())

renderer = HighlighterRenderer()
md = m.Markdown(renderer, extensions=('fenced-code','tables','highlight','quote',))


def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()

# 计算加密cookie:
def user2cookie(user, max_age):
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)


def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


async def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid.
    '''
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None


def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p


@get('/')
async def index(request, *, tag=None):
    # summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    # blogs = [
    #     Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
    #     Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
    #     Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    # ]
    tags = await Tag.findAll()
    if tag:
        blogs = await Blog.findIn2Tables('tagmap', 'blogs', 'tagmap.blog_id=blogs.id', 'tagmap.tag_id=?', int(tag), orderBy='created_at desc')
    else:
        blogs = await Blog.findAll(orderBy='created_at desc')
    return {
        '__template__': 'blogs.html',
        'blogs': blogs,
        'tags':tags
    }



@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = md(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }


@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }


@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }


@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r


@get('/manage/blogs/create')
async def manage_create_blog():
    tags = await Tag.findAll()
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs',
        'tags': tags
    }


@get('/manage/blogs/edit')
async def manage_edit_blog(*, id):
    tags = await Tag.findAll()
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id,
        'tags': tags
    }


@post('/api/users')
async def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    # check passwd:
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content, tags):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    for each in [str(x) for x in tags]:
        t = Tagmap(blog_id=blog.id, tag_id=int(each))
        await  t.save()
    return blog


@post('/api/blogs/{id}')
async def update_blog(id, request, *, name, summary, content, tags):
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    if not tags:
        raise APIValueError('tags', 'tags cannot be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    tags_old = await Tagmap.findAll("blog_id=?", [id])
    if tags_old:
        old_list = [str(x.tag_id) for x in tags_old]
        tags_new = [str(x) for x in tags]
        tags = list.copy(tags_new)
        print(old_list,tags_new)
        tags_new.extend(old_list)
        tags_set = list(set(tags_new))
        for each in tags_set:
            if each not in old_list:
                t = Tagmap(blog_id=id, tag_id=int(each))
                await  t.save()
            elif each not in tags:
                tags_to_remove = await Tagmap.findAll('blog_id=? and tag_id=?', [id, int(each)])
                for x in tags_to_remove:
                    await x.remove()
    else:
        for each in tags:
            t = Tagmap(blog_id=id, tag_id=int(each))
            await  t.save()
    return blog


@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    tag_list = []
    blog = await Blog.find(id)
    tags = await Tagmap.findAll("blog_id=?", [id])
    for each in tags:
        tag_list.append(each.tag_id)
    blog['tags'] = tag_list
    return blog


@get('/api/comments')
async def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    # await time.sleep(10)
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)


@get('/api/blogs')
async def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = await Blog.findNumber('count(id)')
    # await time.sleep(10)
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


@get('/api/users')
async def api_users(*, page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    # await time.sleep(10)
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, users=users)


@get('/api/tags')
async def api_tags():
    tags = await Tag.findAll()
    return dict(tags=tags)


@get('/api/tags/add')
async def api_add_tags(request, *, tag_name):
    check_admin(request)
    if not tag_name:
        raise APIValueError('tag_name', 'Tag name cannot be empty')
    t = Tag(tag_name=tag_name)
    await t.save()
    return dict(tag=t)


@get('/api/tags/remove')
async def api_remove_tags(request, *, tag_id):
    check_admin(request)
    t = await Tag.find(tag_id)
    if t is None:
        raise APIResourceNotFoundError('Tag')
    await t.remove()
    return dict(tag_id=tag_id)


'''
@get('/api/blogsviatag/{tag}')
async def api_get_blogs_via_tag(*, tag):
    tag = {
        "programme": 1,
        "game": 2,
        "cuthand": 3,
        "coins": 4,
    }

'''

@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }

@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }


@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }

@get('/manage/tags')
async def manage_tags():
    return  {
        '__template__': 'manage_tags.html'
    }

@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
    user=request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
    await comment.save()
    return comment


@post('/api/users/{id}/delete')
async def api_delete_users(id, request):
    check_admin(request)
    u = await User.find(id)
    if u is None:
        raise APIResourceNotFoundError('User')
    await u.remove()
    return dict(id=id)


@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
    check_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    await c.remove()
    return dict(id=id)


@get('/coinmarket')
def coinmarket():
    return {
        '__template__': 'coinmarketindex.html'
    }