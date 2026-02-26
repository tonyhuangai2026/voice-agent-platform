import { useState, useEffect } from 'react';
import { Card, Button, Modal, Form, Input, Select, Tag, Space, Row, Col, Typography, message, Segmented, Empty } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, AppstoreOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { useProject } from '../contexts/ProjectContext';
import { createProject, updateProject, deleteProject, listProjects } from '../api';
import type { Project } from '../types';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const PROJECT_TYPES = [
  { label: 'Debt Collection', value: 'collection' },
  { label: 'Marketing Campaign', value: 'marketing' },
  { label: 'Customer Survey', value: 'survey' },
  { label: 'Notification', value: 'notification' },
  { label: 'Other', value: 'other' },
];

const PROJECT_TYPE_COLORS: Record<string, string> = {
  collection: 'purple',
  marketing: 'blue',
  survey: 'green',
  notification: 'orange',
  other: 'default',
};

export function ProjectManagement() {
  const { projects, setProjects, setCurrentProject } = useProject();
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [form] = Form.useForm();

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    setLoading(true);
    try {
      const data = await listProjects();
      setProjects(data.projects);
    } catch (error) {
      message.error('Failed to load projects');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingProject(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (project: Project) => {
    setEditingProject(project);
    form.setFieldsValue({
      project_name: project.project_name,
      project_type: project.project_type,
      description: project.description,
      status: project.status,
    });
    setModalVisible(true);
  };

  const handleDelete = async (project: Project) => {
    Modal.confirm({
      title: 'Archive Project',
      content: `Are you sure you want to archive "${project.project_name}"? This will set its status to archived.`,
      onOk: async () => {
        try {
          await deleteProject(project.project_id);
          message.success('Project archived successfully');
          loadProjects();
        } catch (error) {
          message.error('Failed to archive project');
          console.error(error);
        }
      },
    });
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      if (editingProject) {
        await updateProject(editingProject.project_id, values);
        message.success('Project updated successfully');
      } else {
        const result = await createProject(values);
        message.success('Project created successfully');
        // Auto-select newly created project
        setCurrentProject(result.project);
      }

      setModalVisible(false);
      loadProjects();
    } catch (error) {
      message.error('Failed to save project');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const ProjectCard = ({ project }: { project: Project }) => (
    <Card
      className="glass-card fade-in"
      hoverable
      style={{
        height: '100%',
        borderRadius: 12,
      }}
      actions={[
        <Button
          key="edit"
          type="text"
          icon={<EditOutlined />}
          onClick={() => handleEdit(project)}
        >
          Edit
        </Button>,
        <Button
          key="delete"
          type="text"
          danger
          icon={<DeleteOutlined />}
          onClick={() => handleDelete(project)}
        >
          Archive
        </Button>,
      ]}
    >
      <Space direction="vertical" size="small" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Title level={4} style={{ margin: 0 }}>
            {project.project_name}
          </Title>
          <Tag color={project.status === 'active' ? 'green' : 'default'}>
            {project.status}
          </Tag>
        </div>

        <Tag color={PROJECT_TYPE_COLORS[project.project_type]}>
          {PROJECT_TYPES.find(t => t.value === project.project_type)?.label || project.project_type}
        </Tag>

        <Paragraph
          ellipsis={{ rows: 3 }}
          type="secondary"
          style={{ marginBottom: 8, minHeight: 60 }}
        >
          {project.description || 'No description'}
        </Paragraph>

        <Space size="large" style={{ fontSize: 12 }}>
          <Text type="secondary">
            Created: {new Date(project.created_at).toLocaleDateString()}
          </Text>
        </Space>
      </Space>
    </Card>
  );

  return (
    <div>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={2} style={{ margin: 0 }}>
            Project Management
          </Title>
          <Text type="secondary">Manage your outbound calling projects</Text>
        </div>

        <Space>
          <Segmented
            options={[
              { label: 'Grid', value: 'grid', icon: <AppstoreOutlined /> },
              { label: 'List', value: 'list', icon: <UnorderedListOutlined /> },
            ]}
            value={viewMode}
            onChange={(value) => setViewMode(value as 'grid' | 'list')}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreate}
            className="gradient-button"
            style={{ height: 40 }}
          >
            New Project
          </Button>
        </Space>
      </div>

      {projects.length === 0 ? (
        <Card className="glass-card" style={{ textAlign: 'center', padding: 48 }}>
          <Empty
            description={
              <Space direction="vertical">
                <Text>No projects yet</Text>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                  Create Your First Project
                </Button>
              </Space>
            }
          />
        </Card>
      ) : viewMode === 'grid' ? (
        <Row gutter={[16, 16]}>
          {projects.map((project) => (
            <Col xs={24} sm={12} lg={8} xl={6} key={project.project_id}>
              <ProjectCard project={project} />
            </Col>
          ))}
        </Row>
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {projects.map((project) => (
            <Card
              key={project.project_id}
              className="glass-card fade-in"
              hoverable
              style={{ borderRadius: 12 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space size="large">
                  <div>
                    <Title level={5} style={{ margin: 0 }}>
                      {project.project_name}
                    </Title>
                    <Text type="secondary">{project.description || 'No description'}</Text>
                  </div>
                  <Tag color={PROJECT_TYPE_COLORS[project.project_type]}>
                    {PROJECT_TYPES.find(t => t.value === project.project_type)?.label || project.project_type}
                  </Tag>
                  <Tag color={project.status === 'active' ? 'green' : 'default'}>
                    {project.status}
                  </Tag>
                </Space>

                <Space>
                  <Button icon={<EditOutlined />} onClick={() => handleEdit(project)}>
                    Edit
                  </Button>
                  <Button danger icon={<DeleteOutlined />} onClick={() => handleDelete(project)}>
                    Archive
                  </Button>
                </Space>
              </div>
            </Card>
          ))}
        </Space>
      )}

      <Modal
        title={editingProject ? 'Edit Project' : 'Create New Project'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        confirmLoading={loading}
        width={600}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 24 }}>
          <Form.Item
            name="project_name"
            label="Project Name"
            rules={[{ required: true, message: 'Please enter project name' }]}
          >
            <Input placeholder="e.g., Q1 Collection Campaign" />
          </Form.Item>

          <Form.Item
            name="project_type"
            label="Project Type"
            rules={[{ required: true, message: 'Please select project type' }]}
          >
            <Select options={PROJECT_TYPES} placeholder="Select project type" />
          </Form.Item>

          <Form.Item name="description" label="Description">
            <TextArea
              rows={4}
              placeholder="Describe the purpose and scope of this project"
            />
          </Form.Item>

          {editingProject && (
            <Form.Item
              name="status"
              label="Status"
              rules={[{ required: true }]}
            >
              <Select>
                <Select.Option value="active">Active</Select.Option>
                <Select.Option value="inactive">Inactive</Select.Option>
                <Select.Option value="archived">Archived</Select.Option>
              </Select>
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
