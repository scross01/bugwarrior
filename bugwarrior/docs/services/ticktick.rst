TickTick
========

You can import tasks from `TickTick <https://ticktick.com/>`_ using
the ``ticktick`` service name.

Additional Dependencies
-----------------------

Install packages needed for TickTick support with:

.. code:: bash

   pip install bugwarrior[ticktick]

Authentication
--------------

The TickTick service uses API token authentication.

API Token Authentication
++++++++++++++++++++++++

To authenticate, use your TickTick API token, which you can obtain from your TickTick account settings:

.. config::

    [my_ticktick]
    service = ticktick
    ticktick.token = your_api_token_from_ticktick_settings

**To get your API token:**

1. Log in to your TickTick account
2. Go to **Account Settings** > **API Token**
3. Copy your API token
4. Paste it into your bugwarrior configuration

This is currently the only supported authentication method for the TickTick service.

Service Features
----------------

Project filtering
+++++++++++++++++

You can filter tasks by specific projects using the ``project_filter`` option:

.. config::
    :fragment: ticktick

    ticktick.project_filter = inbox,project_id_1,project_id_2

This will only import tasks from the specified project IDs. Leave empty to import from all projects.

To find the project Id select the task List in TickTick web app to find the unique Id in the URL. ``inbox`` is a special project id used for the TickTick Inbox.

Priority mapping
++++++++++++++++

TickTick task priorities are mapped to the taskwarrior priorities
``H``, ``M``, and ``L`` respectively:

- None: No priority mapping
- Low (1): L
- Medium (3): M  
- High (5): H

You can set a default priority for tasks without explicit priority:

.. config::
    :fragment: ticktick

    ticktick.default_priority = M

Due and Start Date Mappings
+++++++++++++++++++++++++++++++

By default the TickTick task due date is mapped to the taskwarrior ``due`` date field and TickTick start date
is available as a UDA.

You can alter the date mapping using ``due_template`` and ``scheduled_template`` configuration options.

.. config::
    :fragment: ticktick

    ticktick.due_template = {{ticktickduedate}}
    ticktick.scheduled_template = {{ticktickstartdate}}

Import Tags as Labels
++++++++++++++++++++

TickTick allows you to attach `tags <https://ticktick.com/guide/tags>` 
to tasks; to use those tags as labels, you can use the ``import_labels_as_tags`` option:

.. config::
    :fragment: ticktick

    ticktick.import_labels_as_tags = True

Also, if you would like to control how these tags are created, you can
specify a template used for converting the TickTick tag into a Taskwarrior
tag.

For example, to prefix all incoming tags with the string 'ticktick_' (perhaps
to differentiate them from any existing tags you might have), you could
add the following configuration option:

.. config::
    :fragment: ticktick
    
    ticktick.label_template = ticktick_{{tag}}

In addition to the context variable ``{{tag}}``, you also have access
to all fields on the Taskwarrior task if needed.

.. note::
   See :ref:`field_templates` for more details regarding how templates
   are processed.

Provided UDA Fields
-------------------

.. udas:: bugwarrior.services.ticktick.TickTickIssue