"""Read-only schema preflight tests for the NocoBase talent pool."""

import unittest

from features.nocobase_sync.client import NocoBaseError


def swagger_document():
    paths = {}
    for action in ("list", "get", "create", "update", "destroy"):
        paths[f"/campus_talent_pool:{action}"] = {
            "get" if action in ("list", "get") else "post": {"responses": {"200": {}}}
        }
    relations = {
        "Education_Background": "hasMany",
        "Work_experience": "hasMany",
        "Project_Experience": "hasMany",
        "biographical_notes": "belongsToMany",
    }
    for relation, association in relations.items():
        for action in ("list", "get", "create", "update", "destroy", "set", "remove", "toggle"):
            paths[f"/campus_talent_pool/{{collectionIndex}}/{relation}:{action}"] = {
                "x-association-type": association,
                "get" if action in ("list", "get") else "post": {"responses": {"200": {}}},
            }
    def fields(items):
        return {key: {"type": "string", "title": title, **extra} for key, title, extra in items}
    schemas = {
        "campus_talent_pool": {
            "type": "object", "properties": {
                "id": {"type": "integer", "title": "ID"},
                "name": {"type": "string", "title": "姓名"},
                "Number": {"type": "string", "title": "档案编号"},
                "phone": {"type": "string", "title": "联系方式"},
                "gender": {"type": "string", "title": "性别"},
                "birthday": {"type": "string", "title": "出生日期"},
                "age": {"type": "string", "title": "年龄"},
                "email": {"type": "string", "title": "邮箱"},
                "political_status": {"type": "string", "title": "政治面貌"},
                "area": {"type": "string", "title": "籍贯/居住地"},
                "Type": {"type": "string", "title": "招聘类型"},
                "detailed": {"type": "string", "title": "其他渠道详细"},
                "post": {"type": "string", "title": "投递岗位"},
                "Other_job_titles": {"type": "string", "title": "其他岗位名称"},
                "channel": {"type": "string", "title": "校园招聘渠道"},
                "Social_recruitment_channels": {"type": "string", "title": "社会招聘渠道"},
            },
        },
        "campus_talent_pool.Education_Background": {
            "type": "object", "x-association-type": "hasMany", "properties": fields((
                ("degree_key", "学历", {}), ("school_key", "毕业院校", {}),
                ("major_key", "专业", {}), ("enroll_key", "入学时间", {"format": "date"}),
                ("graduate_key", "毕业日期", {"format": "date"}),
            )),
        },
        "campus_talent_pool.Work_experience": {
            "type": "object", "x-association-type": "hasMany", "properties": fields((
                ("company_key", "工作单位", {}), ("position_key", "岗位", {}),
                ("work_start_key", "开始时间", {"format": "date"}),
                ("work_end_key", "结束时间", {"format": "date"}),
                ("work_description_key", "工作描述", {}),
            )),
        },
        "campus_talent_pool.Project_Experience": {
            "type": "object", "x-association-type": "hasMany", "properties": fields((
                ("project_key", "项目名称", {}), ("role_key", "担任角色", {}),
                ("project_start_key", "开始时间", {"format": "date"}),
                ("project_end_key", "结束时间", {"format": "date"}),
                ("project_description_key", "项目描述", {}),
            )),
        },
        "campus_talent_pool.biographical_notes": {
            "type": "object", "x-association-type": "belongsToMany", "properties": {
                "id": {"type": "integer", "title": "ID"},
            },
        },
    }
    return {"openapi": "3.0.0", "paths": paths, "components": {"schemas": schemas}}


class FakeClient:
    def __init__(self, document):
        self.document = document
        self.calls = []

    def request(self, action, **kwargs):
        self.calls.append((action, kwargs))
        return self.document


class NocoBasePreflightTests(unittest.TestCase):
    def test_valid_schema_resolves_all_relation_fields_without_writes(self):
        from features.nocobase_sync.preflight import run_preflight

        client = FakeClient(swagger_document())
        report = run_preflight(client)

        self.assertTrue(report.ok)
        self.assertEqual(dict(report.relation_fields.education), {
            "education": "degree_key", "school_name": "school_key", "major": "major_key",
            "enrollment": "enroll_key", "graduation": "graduate_key",
        })
        self.assertEqual(dict(report.relation_fields.work), {
            "organization": "company_key", "position": "position_key",
            "start_date": "work_start_key", "end_date": "work_end_key",
            "description": "work_description_key",
        })
        self.assertEqual(dict(report.relation_fields.project), {
            "project_name": "project_key", "role": "role_key",
            "start_date": "project_start_key", "end_date": "project_end_key",
            "description": "project_description_key",
        })
        self.assertEqual(client.calls, [("swagger:get", {"params": {"ns": "collections/campus_talent_pool"}})])
        self.assertTrue(all(word not in client.calls[0][0] for word in ("create", "update", "destroy", "set", "toggle")))
        with self.assertRaises(TypeError):
            report.relation_fields.education["education"] = "changed"

    def test_duplicate_title_missing_field_and_wrong_field_type_are_rejected(self):
        from features.nocobase_sync.preflight import run_preflight

        mutations = []
        duplicate = swagger_document()
        duplicate["components"]["schemas"]["campus_talent_pool.Work_experience"]["properties"]["duplicate"] = {
            "type": "string", "title": "岗位",
        }
        mutations.append(duplicate)
        missing = swagger_document()
        del missing["components"]["schemas"]["campus_talent_pool.Education_Background"]["properties"]["major_key"]
        mutations.append(missing)
        wrong_type = swagger_document()
        wrong_type["components"]["schemas"]["campus_talent_pool.Project_Experience"]["properties"]["project_key"]["type"] = "integer"
        mutations.append(wrong_type)
        wrong_format = swagger_document()
        wrong_format["components"]["schemas"]["campus_talent_pool.Work_experience"]["properties"]["work_start_key"]["format"] = "email"
        mutations.append(wrong_format)

        for document in mutations:
            with self.subTest(document=document), self.assertRaises(NocoBaseError) as raised:
                run_preflight(FakeClient(document))
            self.assertEqual(raised.exception.kind, "protocol")

    def test_missing_crud_action_and_wrong_association_type_are_rejected(self):
        from features.nocobase_sync.preflight import run_preflight

        missing_action = swagger_document()
        del missing_action["paths"]["/campus_talent_pool:update"]
        wrong_relation = swagger_document()
        wrong_relation["paths"]["/campus_talent_pool/{collectionIndex}/Work_experience:list"]["x-association-type"] = "belongsToMany"
        for document in (missing_action, wrong_relation):
            with self.subTest(document=document), self.assertRaises(NocoBaseError) as raised:
                run_preflight(FakeClient(document))
            self.assertEqual(raised.exception.kind, "protocol")

    def test_missing_relation_path_and_missing_openapi_schemas_are_rejected(self):
        from features.nocobase_sync.preflight import run_preflight

        missing_relation = swagger_document()
        for path in list(missing_relation["paths"]):
            if "/Project_Experience:" in path:
                del missing_relation["paths"][path]
        no_schemas = swagger_document()
        no_schemas["components"] = {}
        for document in (missing_relation, no_schemas, [], None):
            with self.subTest(document=document), self.assertRaises(NocoBaseError) as raised:
                run_preflight(FakeClient(document))
            self.assertEqual(raised.exception.kind, "protocol")


if __name__ == "__main__":
    unittest.main()
