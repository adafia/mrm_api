import graphene

from graphene_sqlalchemy import SQLAlchemyObjectType
from graphql import GraphQLError

from api.room_resource.models import Resource as ResourceModel


class Resource(SQLAlchemyObjectType):

    class Meta:
        model = ResourceModel


class CreateResource(graphene.Mutation):

    class Arguments:
        name = graphene.String(required=True)
        room_id = graphene.Int(required=True)
    resource = graphene.Field(Resource)

    def mutate(self, info, **kwargs):
        resource = ResourceModel(**kwargs)
        resource.save()

        return CreateResource(resource=resource)


class DeleteResource(graphene.Mutation):

    class Arguments:
        resource_id = graphene.Int(required=True)
    resource = graphene.Field(Resource)

    def mutate(self, info, resource_id, **kwargs):
        query_room_resource = Resource.get_query(info)
        exact_room_resource = query_room_resource.filter(
            ResourceModel.id == resource_id).first()

        exact_room_resource.delete()
        return DeleteResource(resource=exact_room_resource)


class Query(graphene.ObjectType):
    resources = graphene.List(Resource)
    get_resources_by_room_id = graphene.List(lambda: Resource,
                                             room_id=graphene.Int())

    def resolve_resources(self, info):
        query = Resource.get_query(info)
        return query.all()

    def resolve_get_resources_by_room_id(self, info, room_id):
        query = Resource.get_query(info)
        check_room = query.filter(ResourceModel.room_id == room_id).first()
        if not check_room:
            raise GraphQLError("Room has no resource yet")

        return query.filter(ResourceModel.room_id == room_id)


class Mutation(graphene.ObjectType):

    create_resource = CreateResource.Field()
    delete_resource = DeleteResource.Field()