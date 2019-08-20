import graphene
from graphene_sqlalchemy import (SQLAlchemyObjectType)
from sqlalchemy import func, exc
from graphql import GraphQLError

from api.user.models import User as UserModel
from api.notification.models import Notification as NotificationModel
from helpers.auth.user_details import get_user_from_db
from helpers.auth.authentication import Auth
from utilities.validator import verify_email
from helpers.pagination.paginate import Paginate, validate_page
from helpers.auth.error_handler import SaveContextManager
from helpers.email.email import notification
from helpers.user_filter.user_filter import user_filter
from utilities.utility import update_entity_fields
from api.role.schema import Role
from api.role.models import Role as RoleModel
from api.location.models import Location as LocationModel


class User(SQLAlchemyObjectType):
    """
        Autogenerated return type of a user
    """
    class Meta:
        model = UserModel


class CreateUser(graphene.Mutation):
    """
        Mutation to create a user
    """
    class Arguments:
        email = graphene.String(required=True)
        location = graphene.String(required=False)
        name = graphene.String(required=True)
        picture = graphene.String()

    user = graphene.Field(User)

    def mutate(self, info, **kwargs):
        user = UserModel(**kwargs)
        if not verify_email(user.email):
            raise GraphQLError("This email is not allowed")
        payload = {
            'model': UserModel, 'field': 'email', 'value':  kwargs['email']
        }
        with SaveContextManager(user, 'User email', payload):
            notification_settings = NotificationModel(user_id=user.id)
            notification_settings.save()
            return CreateUser(user=user)


class PaginatedUsers(Paginate):
    """
        Paginated users data
    """
    users = graphene.List(User)

    def resolve_users(self, info):
        page = self.page
        per_page = self.per_page
        query = User.get_query(info)
        active_user = query.filter(UserModel.state == "active")
        exact_query = user_filter(active_user, self.filter_data)
        if not page:
            return exact_query.order_by(func.lower(UserModel.email)).all()
        page = validate_page(page)
        self.query_total = exact_query.count()
        result = exact_query.order_by(
            func.lower(UserModel.name)).limit(per_page).offset(page * per_page)
        if result.count() == 0:
            return GraphQLError("No users found")
        return result


class Query(graphene.ObjectType):
    """
        Returns PaginatedUsers
    """
    users = graphene.Field(
        PaginatedUsers,
        page=graphene.Int(),
        per_page=graphene.Int(),
        location_id=graphene.Int(),
        role_id=graphene.Int(),
        description="Returns a list of paginated users and accepts arguments\
            \n- page: Field with the users page\
            \n- per_page: Field indicating users per page\
            \n- location_id: Field with the unique key of user's location\
            \n- role_id: Field with the unique key of the user role"
    )
    user = graphene.Field(
        lambda: User,
        email=graphene.String(),
        description="Query to get a specific user using the user's email\
            accepts the argument\n- email: Email of a user")

    user_by_name = graphene.List(
        User,
        user_name=graphene.String(),
        description="Returns user details and accepts the argument\
            \n- user_name: The name of the user"
    )

    def resolve_users(self, info, **kwargs):
        # Returns all users
        response = PaginatedUsers(**kwargs)
        return response

    @Auth.user_roles('Admin', 'Default User', 'Super Admin')
    def resolve_user(self, info, email):
        # Returns a specific user.
        query = User.get_query(info)
        return query.filter(UserModel.email == email).first()

    @Auth.user_roles('Admin', 'Super Admin')
    def resolve_user_by_name(self, info, user_name):
        user_list = []
        user_name = ''.join(user_name.split()).lower()
        if not user_name:
            raise GraphQLError("Please provide the user name")
        active_users = User.get_query(info).filter_by(state="active")
        for user in active_users:
            exact_user_name = user.name.lower().replace(" ", "")
            if user_name in exact_user_name:
                user_list.append(user)
        if not user_list:
            raise GraphQLError("User not found")

        return user_list


class DeleteUser(graphene.Mutation):
    """
        Returns payload on deleting a user
    """

    class Arguments:
        email = graphene.String(required=True)
        state = graphene.String()

    user = graphene.Field(User)

    @Auth.user_roles('Admin', 'Super Admin')
    def mutate(self, info, email, **kwargs):
        query_user = User.get_query(info)
        active_user = query_user.filter(UserModel.state == "active")
        exact_query_user = active_user.filter(UserModel.email == email).first()
        user_from_db = get_user_from_db()
        if not verify_email(email):
            raise GraphQLError("Invalid email format")
        if not exact_query_user:
            raise GraphQLError("User not found")
        if user_from_db.email == email:
            raise GraphQLError("You cannot delete yourself")
        update_entity_fields(exact_query_user, state="archived", **kwargs)
        exact_query_user.save()
        return DeleteUser(user=exact_query_user)


class ChangeUserRole(graphene.Mutation):
    """
        Returns payload on creating a user role
    """
    class Arguments:

        email = graphene.String(required=True)
        role_id = graphene.Int()

    user = graphene.Field(User)

    @Auth.user_roles('Admin', 'Super Admin')
    def mutate(self, info, email, **kwargs):
        query_user = User.get_query(info)
        active_user = query_user.filter(UserModel.state == "active")
        exact_user = active_user.filter(UserModel.email == email).first()
        if not exact_user:
            raise GraphQLError("User not found")

        new_role = RoleModel.query.filter_by(id=kwargs['role_id']).first()
        if not new_role:
            raise GraphQLError('invalid role id')

        current_user_role = exact_user.roles[0].role
        if new_role.role == current_user_role:
            raise GraphQLError('This role is already assigned to this user')

        exact_user.roles[0] = new_role
        exact_user.save()

        if not notification.send_changed_role_email(
                email, exact_user.name, new_role.role):
            raise GraphQLError("Role changed but email not sent")

        return ChangeUserRole(user=exact_user)


class ChangeUserLocation(graphene.Mutation):
    """
        Returns user details on changing the user's location
    """
    class Arguments:
        email = graphene.String(required=True)
        location_id = graphene.Int(required=True)

    user = graphene.Field(User)

    @Auth.user_roles('Admin', 'Super Admin')
    def mutate(self, info, **kwargs):
        email = kwargs['email']
        location_id = kwargs['location_id']
        query_user = User.get_query(info)
        user = query_user.filter(
            UserModel.state == "active", UserModel.email == email).first()
        if not user:
            raise GraphQLError("User not found")
        new_location = LocationModel.query.filter_by(
            id=location_id, state="active").first()
        if not new_location:
            raise GraphQLError('the location supplied does not exist')
        if user.location == new_location.name:
            raise GraphQLError('user already in this location')
        user.location = new_location.name
        user.save()
        return ChangeUserLocation(user=user)


class SetUserLocation(graphene.Mutation):
    """
        Mutation for users to set their location
    """
    class Arguments:
        location_id = graphene.Int(required=True)

    user = graphene.Field(User)

    @Auth.user_roles('Admin', 'Super Admin', 'Default User')
    def mutate(self, info, **kwargs):
        logged_in_user = get_user_from_db()
        location_id = kwargs['location_id']
        query_user = User.get_query(info)
        user = query_user.filter(
            UserModel.state == "active", UserModel.id == logged_in_user.id).first() # noqa
        if user.location:
            raise GraphQLError('This user already has a location set.')
        new_location = LocationModel.query.filter_by(
            id=location_id, state="active").first()
        if not new_location:
            raise GraphQLError('The location supplied does not exist')
        user.location = new_location.name
        user.save()
        return SetUserLocation(user=user)


class CreateUserRole(graphene.Mutation):
    """
        Returns payload of creating a role for a user
    """

    class Arguments:
        user_id = graphene.Int(required=True)
        role_id = graphene.Int(required=True)
    user_role = graphene.Field(User)

    def mutate(self, info, **kwargs):
        try:
            user = User.get_query(info)
            exact_user = user.filter_by(id=kwargs['user_id']).first()

            if not exact_user:
                raise GraphQLError('User not found')

            role = Role.get_query(info)
            exact_role = role.filter_by(id=kwargs['role_id']).first()

            if not exact_role:
                raise GraphQLError('Role id does not exist')

            exact_user.roles.append(exact_role)
            exact_user.save()

            return CreateUserRole(user_role=exact_user)
        except exc.ProgrammingError:
            raise GraphQLError("The database cannot be reached")


class InviteToConverge(graphene.Mutation):
    """
        Returns payload on inviting users to converge
    """
    class Arguments:
        email = graphene.String(
            required=True, description="Email field of a user")

    email = graphene.String()

    @Auth.user_roles('Admin', 'Super Admin')
    def mutate(self, info, email):
        if not verify_email(email):
            raise GraphQLError("Use a valid andela email")
        query_user = User.get_query(info)
        active_user = query_user.filter(UserModel.state == "active")
        user = active_user.filter(UserModel.email == email).first()
        if user:
            raise GraphQLError("User already joined Converge")
        admin = get_user_from_db()
        notification.email_invite(email, admin.__dict__["name"])
        return InviteToConverge(email=email)


class Mutation(graphene.ObjectType):
    """
        Mutation to create, delete, change_role,
         invite_to_converge and create_user_role
    """
    create_user = CreateUser.Field(
        description="Creates a new user with the arguments\
            \n- email: The email field of the user[required]\
            \n- location: The location field of a user\
            \n- name: The name field of a user[required]\
            \n- picture: The picture field of a user")
    delete_user = DeleteUser.Field(
        description="Deletes a user having arguments\
            \n- email: The email field of a user[required]\
            \n- state: Check if the user is active, archived or deleted")
    change_user_role = ChangeUserRole.Field(
        description="Changes the role of a user and takes arguments\
            \n- email: The email field of a user[required]\
            \n- role_id: unique identifier of a user role")
    change_user_location = ChangeUserLocation.Field(
        description="Changes the location of a user and accepts the arguments\
            \n- email: The email field of the user[required]\
            \n- location_id: the new location of the user[required]")
    set_user_location = SetUserLocation.Field(
        description="sets the location of a user with no location and accepts arguments\
           \n- location_id: the new location of the user[required]")
    invite_to_converge = InviteToConverge.Field(
        description="Invites a new user to converge \
            \n- email: The email field of a user[required]")
    create_user_role = CreateUserRole.Field(
        description="Assigns a user a role \
            \n- user_id: The  unique identifier of the user\
            \n- role_id:  unique identifier of a user role")
