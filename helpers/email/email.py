from .email_setup import SendEmail
from config import Config
from flask import render_template
from api.room.models import Room as RoomModel


class EmailNotification:
    """
    Send email notifications
    """
    def send_email_notification(
        self, **kwargs
    ):
        """
        send email notifications after a given activity has occured
        """
        recipients = kwargs.get('email')

        email = SendEmail(
            kwargs.get('subject'), recipients,
            render_template(
                kwargs.get('template'),
                location_name=kwargs.get('location_name'),
                user_name=kwargs.get('user_name'),
                room_name=kwargs.get('room_name'),
                event_title=kwargs.get('event_title'),
                event_reject_reason=kwargs.get('event_reject_reason'),
                new_role=kwargs.get('new_role'),
                domain=kwargs.get('domain')
            ))

        return email.send()

    def email_invite(self, email, admin):
        """
        send email invite for user to join converge
        """
        return EmailNotification.send_email_notification(
            self, email=[email], subject="Invitation to join Converge",
            template='invite.html',
            user_name=admin, domain=Config.DOMAIN_NAME
        )

    def event_cancellation_notification(
        self, event, room_id, event_reject_reason
    ):
        """
        send email notifications on event rejection
         :params
            - event: The event being rejected
            - room_id: Id of the room rejecting the event
            - event_reject_reason: Reason for rejecting the event
        """
        attendees = event['attendees']
        email = [attendee['email'] for attendee in attendees]
        event_title = event['summary']
        room = RoomModel.query.filter_by(id=room_id).first()
        room_name = room.name
        subject = 'Your room reservation was rejected'
        template = 'event_cancellation.html'
        return EmailNotification.send_email_notification(
            self,
            email=email,
            subject=subject,
            template=template,
            room_name=room_name,
            event_title=event_title,
            event_reject_reason=event_reject_reason
        )

    def send_changed_role_email(self, user_email, user_name, new_role):
        """
        send email notification when user role is changed
            :params
                - user_email: the email of the user whose role is changed
                - user_name: the name of the user whose role is changed
        """

        return EmailNotification.send_email_notification(
            self,
            email=[user_email],
            subject='Converge - Your role has been changed',
            user_name=user_name,
            template='change_role.html',
            new_role=new_role,
            domain=Config.DOMAIN_NAME
        )


notification = EmailNotification()
