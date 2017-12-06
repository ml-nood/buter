"""
Application 控制器

add on 2017-11-14 16:46:35
"""
from flask import jsonify, request

from buter import Result, db, ServiceException, getAttachPath
from buter.app import services
from buter.logger import LOG
from buter.util.FlaskTool import Q
from buter.util.Utils import copyEntityBean, notEmptyStr

from . import appBp
from ..models import Application, Resource


@appBp.route("/")
def index():
    return "Hello, welcome to application index page"


@appBp.route("/<int:aid>")
def detail(aid):
    return jsonify(Application.query.get(aid))


@appBp.route("/list", methods=['GET', 'POST'])
def lists():
    datas = Application.query.all()
    return jsonify(Result.ok(data=datas))


@appBp.route("/edit", methods=['GET', 'POST'])
@appBp.route("/add", methods=['GET', 'POST'])
def add():
    """
    录入新的应用
    :return:
    """
    ps = request.values
    name = ps.get('name')
    version = ps.get('version', default="1.0.0")

    notEmptyStr(name=name, version=version)

    id = ps.get('id')

    app = Application(name=name, id=id, version=version, remark=ps.get('remark'))

    if id and int(id) > 0:
        oldApp = Application.query.get(id)
        if oldApp is None:
            raise ServiceException("ID=%d 的应用不存在故不能编辑" % id)

        copyEntityBean(app, oldApp)
    else:
        # 判断应用名是否重复
        oldApp = Application.query.getOne(name=name)
        if oldApp:
            raise ServiceException("应用 %s 已经存在，不能重复录入" % name)

        db.session.add(app)

    db.session.commit()

    op = "录入" if id is 0 else "编辑"
    LOG.info("%s应用 %s" % (op, app))
    return jsonify(
        Result.ok(
            "应用 %s %s成功(版本=%s)" % (name, op, version),
            app.id
        )
    )


@appBp.route("/delete", methods=['GET', 'POST'])
@appBp.route("/delete/<aid>", methods=['GET', 'POST'])
def delete(aid=None):
    aid = aid if aid is not None else Q('ids', type=int)
    LOG.info("客户端请求删除 ID=%d 的应用..." % aid)

    app = Application.query.get(aid)
    if app:
        db.session.delete(app)
        db.session.commit()
        LOG.info("删除 ID=%d 的应用成功" % aid)
        return jsonify(Result.ok())
    else:
        raise ServiceException("ID=%d 的应用不存在故不能执行删除操作..." % aid)


@appBp.route("/stats", methods=['GET', 'POST'])
def stats():
    """
    查看应用状态，接受的参数为`name=n1,n2,n3`

    //查询成功返回示例
    {
        "success":true,
        "data":{
            "name1":-1,
            "name2":0,
            "name3":1
        }
    }
    //查询失败返回示例
    {
        "success":false,
        "message":"无法查询容器状态，请检查 Docker 是否运行"
    }
    :return:
    """
    names = Q('names', "", str).split(",")
    containers = services.list_all_container(True)
    LOG.info("当前所有容器状态：%s", containers)
    data = dict((n, -1 if n not in containers else 1 if containers[n]['stat'] == 'running' else 0) for n in names)
    return jsonify(Result.ok(data=data))


@appBp.route("/upload", methods=['POST'])
def uploadNewVersion():
    """
    上传 app 新版本资源

    1. 若 app 存在（request.id > 0)
        从数据库中获取对应的 app

    2. 若 app 不存在（request.id=0）
        则 request.name 不能为空
        创建新的 app

    :return:
    """
    file = request.files['file']
    if file is None:
        raise ServiceException("无法检测到文件，请先上传")

    app = __detect_app()
    auto_create = app.id is None
    if auto_create:
        db.session.add(app)

    # 保存文件到 attachments 目录
    saved_file = getAttachPath(file.filename)
    LOG.info("上传 %s 到 %s" % (file.filename, saved_file))
    file.save(saved_file)
    resource = Resource.fromFile(saved_file, app)
    db.session.add(resource)

    name, files = services.load_from_file(saved_file, app, Q('update', False, bool))

    db.session.commit()
    return jsonify(Result.ok("%s 应用新版本部署成功" % name, files))


@appBp.route("/operate/<name>/<op>", methods=['GET', 'POST'])
def operate(name, op):
    if op not in services.OPERATIONS:
        raise ServiceException("无效的操作类型：{} (可选：{})".format(op, services.OPERATIONS))

    LOG.info("即将对容器 %s 执行 %s 操作...", name, op)
    services.do_with_container(name, op)
    return jsonify(Result.ok("{} 执行 {} 操作成功".format(name, op)))


def __detect_app():
    aid = Q('id', 0, int)
    if aid == 0:
        name, version = Q('name'), Q('version', '1.0.0')
        notEmptyStr(name=name, version=version)
        return Application(name=name, version=version)
    else:
        return Application.query.get(aid)
